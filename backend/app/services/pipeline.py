"""
Trading pipeline split into two independent async loops per market:
  - run_sl_monitor()   — runs every 10s, checks SL/TP only (no Claude calls)
  - run_signal_loop()  — runs every 60s, processes all symbols in parallel
"""
import asyncio
import uuid
from datetime import datetime
import structlog
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.db.models import AISignal, KnowledgeEntry
from app.core import redis_client
from app.services.indicators.engine import compute_indicators, should_call_llm
from app.services.ai.signal_generator import generate_signal
from app.services.episode_manager import get_or_create_active_episode, check_episode_completion, update_equity
from app.services.strategy_engine import get_active_strategy_names
from app.services.risk import check_signal, monitor_stop_loss_take_profit, check_daily_loss_limit
from app.services.execution.paper import open_position, close_position
from app.services.market_hours import is_market_open, minutes_to_close
from app.services.knowledge.context_matcher import extract_context_tags, score_entry
from app.config import PROMPT_DEPTH_CONFIG

log = structlog.get_logger()

MARKET_SYMBOLS = {
    "crypto": ["BTCUSDT", "ETHUSDT"],
    "us_stocks": ["AAPL", "NVDA", "SPY"],
    "india_stocks": ["NIFTY50", "RELIANCE"],
    "forex": ["EUR_USD", "USD_INR"],
}
MARKET_INTERVALS = {
    "crypto": "1m",
    "us_stocks": "1m",
    "india_stocks": "1m",
    "forex": "1m",
}
SL_MONITOR_INTERVAL = 10    # seconds — fast loop
SIGNAL_INTERVAL = 60        # seconds — slow loop


async def _get_knowledge_snippets(
    db,
    market: str,
    context_tags: list[str],
    depth_cfg: dict,
) -> tuple[list[str], list[str]]:
    """Context-aware retrieval. Returns (rule_snippets, historical_snippets)."""
    result = await db.execute(
        select(KnowledgeEntry).where(
            (KnowledgeEntry.market == market) | (KnowledgeEntry.market == "all")
        )
    )
    entries = list(result.scalars())

    # Score every entry against current context
    scored = []
    for e in entries:
        s = score_entry(e, context_tags)
        scored.append((s, e))
    scored.sort(key=lambda x: x[0], reverse=True)

    rule_cats = {"risk_management", "risk", "strategy", "regime", "lesson"}
    rules = [e for _, e in scored if e.category in rule_cats]
    history = [e for _, e in scored if e.category not in rule_cats]

    n_rules = depth_cfg.get("knowledge", 2)
    n_hist = depth_cfg.get("historical", 1)

    rule_snippets = [f"{e.title}: {e.content[:120]}" for e in rules[:n_rules]]
    hist_snippets = [f"[{e.category}] {e.title}: {e.content[:250]}" for e in history[:n_hist]]

    # Increment times_referenced for returned entries (fire-and-forget)
    ids_referenced = [e.id for e in rules[:n_rules]] + [e.id for e in history[:n_hist]]
    if ids_referenced:
        try:
            await db.execute(
                update(KnowledgeEntry)
                .where(KnowledgeEntry.id.in_(ids_referenced))
                .values(times_referenced=KnowledgeEntry.times_referenced + 1)
            )
            await db.commit()
        except Exception:
            pass

    return rule_snippets, hist_snippets


async def _process_symbol(
    symbol: str,
    market: str,
    interval: str,
    episode,
    active_strats: list[str],
    knowledge: list[str],
    historical: list[str],
    upcoming_events: list[dict],
    db,
    block_new_positions: bool = False,
) -> float | None:
    """Process one symbol: indicators → pre-filter → signal → position open. Returns mark price."""
    candles = await redis_client.zrange_candles(symbol, interval)
    if not candles:
        return None

    indicators = await compute_indicators(symbol, interval)
    if not indicators:
        return None

    price = indicators.get("current_price", 0)

    # ── Layer 1: Indicator pre-filter (zero tokens if flat market) ──────────
    if not should_call_llm(indicators):
        log.debug("signal_skipped_pre_filter", symbol=symbol)
        return price

    # ── Layer 2: Claude/Gemini signal (model from runtime config) ───────────
    result = await db.execute(
        select(AISignal).where(
            AISignal.symbol == symbol,
            AISignal.market == market,
        ).order_by(AISignal.created_at.desc()).limit(2)
    )
    recent_signals = [
        {"action": s.action, "confidence": s.confidence,
         "reasoning": s.reasoning, "created_at": s.created_at.isoformat()}
        for s in result.scalars()
    ]

    signal_data = await generate_signal(
        symbol=symbol, market=market, episode_id=episode.id,
        recent_candles=candles[-10:], indicators=indicators,
        active_strategies=active_strats, recent_signals=recent_signals,
        knowledge_snippets=knowledge,
        historical_snippets=historical,
        upcoming_events=upcoming_events,
    )

    if not signal_data:
        return price

    # Persist signal
    ai_signal = AISignal(
        id=str(uuid.uuid4()), market=market, symbol=symbol,
        action=signal_data["action"], confidence=signal_data["confidence"],
        reasoning=signal_data["reasoning"], risk_note=signal_data.get("risk_note", ""),
        indicators_snapshot=indicators, price_at_signal=price,
        episode_id=episode.id, created_at=datetime.utcnow(),
    )
    db.add(ai_signal)
    await db.commit()

    await redis_client.publish(f"signal:{market}", {
        "market": market, "symbol": symbol,
        "action": signal_data["action"], "confidence": signal_data["confidence"],
        "reasoning": signal_data["reasoning"], "price": price,
    })

    # ── Layer 3: Risk check → open position ─────────────────────────────────
    if block_new_positions:
        log.info("new_position_blocked_near_close", symbol=symbol, market=market)
        return price

    trade_decision = await check_signal(db, episode, signal_data)
    if trade_decision:
        strat_name = active_strats[0] if active_strats else "Default Momentum"
        await open_position(
            db=db, episode_id=episode.id, market=market, symbol=symbol,
            side=trade_decision["side"], leverage=trade_decision["leverage"],
            mark_price=price, notional_usd=trade_decision["notional"],
            strategy_name=strat_name, signal_id=ai_signal.id,
        )

    return price


async def run_sl_monitor(market: str) -> None:
    """Fast loop (10s): checks stop-loss and take-profit on all open positions."""
    log.info("sl_monitor_started", market=market)
    symbols = MARKET_SYMBOLS.get(market, [])
    while True:
        try:
            async with AsyncSessionLocal() as db:
                from app.db.models import Episode
                from app.db.models.episode import EpisodeOutcome as EO
                ep_result = await db.execute(
                    select(Episode).where(
                        Episode.market == market,
                        Episode.outcome == EO.running,
                    ).order_by(Episode.start_at.desc()).limit(1)
                )
                episode = ep_result.scalar_one_or_none()
                if not episode:
                    await asyncio.sleep(SL_MONITOR_INTERVAL)
                    continue

                # Build current price map from Redis
                current_prices: dict[str, float] = {}
                for symbol in symbols:
                    ind = await redis_client.get_json(f"indicators:{symbol}")
                    if ind and ind.get("current_price"):
                        current_prices[symbol] = ind["current_price"]

                to_close = await monitor_stop_loss_take_profit(db, episode, current_prices)
                for trade, reason in to_close:
                    price = current_prices.get(trade.symbol, trade.entry_price)
                    pnl = await close_position(db, trade, price, reason)
                    await update_equity(db, episode, pnl)
                    log.info("position_closed_sl_tp", symbol=trade.symbol, reason=reason, pnl=pnl)

                # Check episode completion
                await db.refresh(episode)
                await check_episode_completion(db, episode)

        except Exception as e:
            log.error("sl_monitor_error", market=market, error=str(e))

        await asyncio.sleep(SL_MONITOR_INTERVAL)


async def run_signal_loop(market: str) -> None:
    """Slow loop (60s): parallel symbol processing → indicator pre-filter → Claude signals."""
    symbols = MARKET_SYMBOLS.get(market, [])
    interval = MARKET_INTERVALS.get(market, "1m")
    log.info("signal_loop_started", market=market, symbols=symbols)

    while True:
        try:
            # ── Guard 1: Market hours ────────────────────────────────────────
            if not is_market_open(market):
                log.debug("signal_loop_market_closed", market=market)
                await asyncio.sleep(SIGNAL_INTERVAL)
                continue

            # ── Guard 2: Pause flag ──────────────────────────────────────────
            if await redis_client.is_bot_paused():
                log.info("signal_loop_paused", market=market)
                await asyncio.sleep(SIGNAL_INTERVAL)
                continue

            # ── Guard 3: Near market close → block new positions ─────────────
            mtc = minutes_to_close(market)
            block_new_positions = mtc is not None and mtc <= 15

            async with AsyncSessionLocal() as db:
                episode = await get_or_create_active_episode(db, market)

                # ── Guard 4: Daily loss limit ────────────────────────────────
                bot_config = await redis_client.get_bot_config()
                daily_loss_pct = float(bot_config.get("daily_loss_limit_pct", 0.10))
                if await check_daily_loss_limit(db, episode, daily_loss_pct):
                    log.warning("daily_loss_limit_triggered_auto_pause", market=market)
                    await redis_client.set_bot_paused(True)
                    await asyncio.sleep(SIGNAL_INTERVAL)
                    continue

                active_strats = await get_active_strategy_names(db, market)

                # ── Context-aware knowledge retrieval ────────────────────────
                world = await redis_client.get_json("world:context") or {}
                upcoming_events = world.get("upcoming_events", [])

                # Use first symbol's indicators as a proxy for context tags
                first_indicators = await redis_client.get_json(f"indicators:{symbols[0]}") if symbols else {}
                context_tags = extract_context_tags(
                    market=market,
                    indicators=first_indicators or {},
                    world=world,
                    upcoming_events=upcoming_events,
                )

                depth = bot_config.get("prompt_depth", "standard")
                depth_cfg = PROMPT_DEPTH_CONFIG.get(depth, PROMPT_DEPTH_CONFIG["standard"])

                rule_snippets, hist_snippets = await _get_knowledge_snippets(
                    db, market, context_tags, depth_cfg
                )

                # Process all symbols in parallel
                await asyncio.gather(
                    *[
                        _process_symbol(
                            symbol, market, interval, episode, active_strats,
                            rule_snippets, hist_snippets, upcoming_events, db,
                            block_new_positions=block_new_positions,
                        )
                        for symbol in symbols
                    ],
                    return_exceptions=True,
                )

                if block_new_positions:
                    log.info("signal_loop_near_close_no_new_positions", market=market, minutes_to_close=mtc)

        except Exception as e:
            log.error("signal_loop_error", market=market, error=str(e))

        await asyncio.sleep(SIGNAL_INTERVAL)
