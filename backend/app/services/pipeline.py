"""
Trading pipeline: per-market loop that connects market data →
indicators → AI signal → risk check → paper execution → episode monitor.
"""
import asyncio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models import AISignal, KnowledgeEntry
from app.core import redis_client
from app.services.indicators.engine import compute_indicators
from app.services.ai.signal_generator import generate_signal
from app.services.episode_manager import get_or_create_active_episode, check_episode_completion, update_equity
from app.services.strategy_engine import get_active_strategy_names
from app.services.risk import check_signal, monitor_stop_loss_take_profit
from app.services.execution.paper import open_position, close_position
import uuid
from datetime import datetime

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


async def _get_knowledge_snippets(db: AsyncSession, market: str, limit: int = 5) -> list[str]:
    result = await db.execute(
        select(KnowledgeEntry).where(
            (KnowledgeEntry.market == market) | (KnowledgeEntry.market == "all")
        ).order_by(KnowledgeEntry.importance.desc()).limit(limit)
    )
    return [f"{k.title}: {k.content[:150]}" for k in result.scalars()]


async def run_market_pipeline(market: str) -> None:
    symbols = MARKET_SYMBOLS.get(market, [])
    interval = MARKET_INTERVALS.get(market, "1m")
    log.info("pipeline_started", market=market, symbols=symbols)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                episode = await get_or_create_active_episode(db, market)
                active_strats = await get_active_strategy_names(db, market)
                knowledge = await _get_knowledge_snippets(db, market)

                current_prices: dict[str, float] = {}

                for symbol in symbols:
                    candles = await redis_client.zrange_candles(symbol, interval)
                    if not candles:
                        continue
                    indicators = await compute_indicators(symbol, interval)
                    if not indicators:
                        continue

                    price = indicators.get("current_price", 0)
                    if price:
                        current_prices[symbol] = price

                    # Fetch recent signals for this symbol
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
                        symbol=symbol,
                        market=market,
                        episode_id=episode.id,
                        recent_candles=candles[-10:],
                        indicators=indicators,
                        active_strategies=active_strats,
                        recent_signals=recent_signals,
                        knowledge_snippets=knowledge,
                    )

                    if not signal_data:
                        continue

                    # Persist signal
                    ai_signal = AISignal(
                        id=str(uuid.uuid4()),
                        market=market,
                        symbol=symbol,
                        action=signal_data["action"],
                        confidence=signal_data["confidence"],
                        reasoning=signal_data["reasoning"],
                        risk_note=signal_data.get("risk_note", ""),
                        indicators_snapshot=indicators,
                        price_at_signal=price,
                        episode_id=episode.id,
                        created_at=datetime.utcnow(),
                    )
                    db.add(ai_signal)
                    await db.commit()

                    await redis_client.publish(f"signal:{market}", {
                        "market": market, "symbol": symbol,
                        "action": signal_data["action"],
                        "confidence": signal_data["confidence"],
                        "reasoning": signal_data["reasoning"],
                        "price": price,
                    })

                    # Risk check
                    gen_result = await db.execute(
                        select(KnowledgeEntry).where(KnowledgeEntry.category == "risk").limit(1)
                    )
                    trade_decision = await check_signal(db, episode, signal_data)

                    if trade_decision:
                        strat_name = active_strats[0] if active_strats else "Default Momentum"
                        trade = await open_position(
                            db=db,
                            episode_id=episode.id,
                            market=market,
                            symbol=symbol,
                            side=trade_decision["side"],
                            leverage=trade_decision["leverage"],
                            mark_price=price,
                            notional_usd=trade_decision["notional"],
                            strategy_name=strat_name,
                            signal_id=ai_signal.id,
                        )

                # Monitor stop-loss / take-profit for all open positions
                to_close = await monitor_stop_loss_take_profit(db, episode, current_prices)
                for trade, reason in to_close:
                    price = current_prices.get(trade.symbol, trade.entry_price)
                    pnl = await close_position(db, trade, price, reason)
                    await update_equity(db, episode, pnl)

                # Refresh episode from DB and check completion
                await db.refresh(episode)
                await check_episode_completion(db, episode)

        except Exception as e:
            log.error("pipeline_error", market=market, error=str(e))

        await asyncio.sleep(60)   # poll every 60 seconds
