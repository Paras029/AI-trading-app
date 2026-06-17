"""
Post-Mortem Agent — Stage 5 of the pipeline. Runs once a Trade settles (win or loss).

1. Pull the related PredictionSignal / ResearchBrief / ModelForecast rows for context.
2. Build context tags + score existing PostMortem rows for "similar past trades" the AI
   should consider (and not repeat verbatim).
3. Call the AI (POSTMORTEM_SYSTEM_PROMPT / build_postmortem_prompt) to classify the failure
   (loss only) and write a lesson.
4. Persist PostMortem. importance>=7 lessons are also mirrored into KnowledgeEntry — same
   pattern as the old episode_manager.py::evolve()'s lesson->knowledge_base promotion.
5. Recompute a CalibrationSnapshot (win_rate/Sharpe/max_drawdown/profit_factor/Brier) over
   the portfolio's settled trades — formulas ported from the old strategy_engine.py's
   update_strategy_stats(), rescoped from per-Strategy to per-Portfolio mode.
6. Every xgboost_retrain_interval settlements, fire-and-forget calibration.train_or_update_model().
7. Publish the new PostMortem to redis_client.publish('postmortem:new', {...}).
"""
import json
import statistics
import uuid
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.config import settings
from app.db.models import (
    Trade, PredictionMarket, PredictionSignal, ResearchBrief, ModelForecast,
    PostMortem, CalibrationSnapshot, KnowledgeEntry, Portfolio,
)
from app.core import redis_client
from app.services.ai import providers
from app.services.ai.prompt_builder import POSTMORTEM_SYSTEM_PROMPT, build_postmortem_prompt
from app.services.knowledge import context_matcher
from app.services.cost_tracker import track_usage
from app.services.prediction import calibration

log = structlog.get_logger()

KNOWLEDGE_IMPORTANCE_THRESHOLD = 7
_settlement_counts: dict[str, int] = {}  # mode -> count since last xgboost retrain, in-process counter


async def _build_lesson(trade: Trade, market: PredictionMarket, signal: PredictionSignal | None,
                         similar_past: list[PostMortem]) -> dict:
    """Calls the AI to analyze the trade; falls back to a heuristic lesson if no AI key
    is configured or the call fails — post-mortems must never block settlement."""
    outcome = "WIN" if (trade.pnl or 0) > 0 else "LOSS"

    trade_dict = {
        "side": trade.side,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "stake_usdc": trade.stake_usdc,
        "pnl": trade.pnl,
        "pnl_pct": trade.pnl_pct,
        "kelly_fraction_used": trade.kelly_fraction_used,
        "full_kelly_fraction": trade.full_kelly_fraction,
        "status": trade.status,
    }
    market_dict = {"question": market.question if market else ""}
    signal_dict = {
        "ensemble_probability": signal.ensemble_probability if signal else 0.0,
        "final_probability": signal.final_probability if signal else 0.0,
        "market_price": signal.market_price if signal else 0.0,
        "edge": signal.edge if signal else 0.0,
        "expected_value": signal.expected_value if signal else 0.0,
        "used_xgboost": signal.used_xgboost if signal else False,
    }
    similar_dicts = [
        {"lesson_title": p.lesson_title, "lesson_body": p.lesson_body}
        for p in similar_past
    ]

    fallback = {
        "analysis": (
            f"Trade settled as a {outcome.lower()} (pnl ${trade.pnl:.2f}). "
            f"No AI key configured — heuristic post-mortem only."
        ),
        "failure_category": None if outcome == "WIN" else "bad_prediction",
        "lesson_title": f"{outcome} on {market.category if market else 'unknown'} market",
        "lesson_body": (
            f"Entered {trade.side} at {trade.entry_price:.3f}, ensemble probability was "
            f"{signal_dict['ensemble_probability']:.3f}, edge {signal_dict['edge']:+.3f}. "
            f"Result: {outcome} with pnl ${trade.pnl:.2f} ({trade.pnl_pct:.1f}%)."
        ),
        "importance": 6 if outcome == "LOSS" else 4,
    }

    if not providers.has_key_for_provider("anthropic") and not providers.has_key_for_provider("google"):
        return fallback

    provider = "anthropic" if providers.has_key_for_provider("anthropic") else "google"
    model = "claude-sonnet-4-6" if provider == "anthropic" else "gemini-2.0-flash"
    prompt = build_postmortem_prompt(trade_dict, market_dict, signal_dict, similar_dicts)

    try:
        if provider == "anthropic":
            raw, usage = await providers.call_anthropic(model, POSTMORTEM_SYSTEM_PROMPT, prompt, 600)
        else:
            raw, usage = await providers.call_gemini(model, POSTMORTEM_SYSTEM_PROMPT, prompt, 600)
        await track_usage(model, "postmortem", usage, market="prediction")

        parsed = json.loads(providers._clean_json(raw))
        importance = parsed.get("importance", 5)
        try:
            importance = max(1, min(10, int(importance)))
        except (TypeError, ValueError):
            importance = 5

        failure_category = parsed.get("failure_category")
        valid_categories = {
            "bad_prediction", "bad_timing", "external_shock",
            "bad_execution", "overweighted_sentiment", "model_overconfidence",
        }
        if outcome == "WIN" or failure_category not in valid_categories:
            failure_category = None if outcome == "WIN" else (failure_category if failure_category in valid_categories else "bad_prediction")

        return {
            "analysis": parsed.get("analysis", fallback["analysis"]),
            "failure_category": failure_category,
            "lesson_title": parsed.get("lesson_title", fallback["lesson_title"]),
            "lesson_body": parsed.get("lesson_body", fallback["lesson_body"]),
            "importance": importance,
        }
    except Exception as e:
        log.warning("postmortem_ai_failed", trade_id=trade.id, error=str(e))
        return fallback


def _compute_calibration_stats(trades: list[Trade]) -> dict:
    """Win-rate / Sharpe / max-drawdown / profit-factor formulas ported verbatim from the
    old strategy_engine.py::update_strategy_stats(), generalized from per-strategy to
    per-portfolio-mode and walked in chronological (settled_at) order for the drawdown calc."""
    pnls = [t.pnl for t in trades if t.pnl is not None]
    n = len(pnls)
    if n == 0:
        return {
            "win_rate": 0.0, "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0,
            "profit_factor": 0.0, "avg_pnl_per_trade": 0.0, "num_trades": 0,
        }

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / n
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else (float("inf") if wins else 0.0)
    # Cap profit_factor for JSON/DB sanity when there are no losses at all.
    if profit_factor == float("inf"):
        profit_factor = 999.0

    if n >= 2:
        mean_pnl = sum(pnls) / n
        std_pnl = statistics.stdev(pnls)
        sharpe = (mean_pnl / std_pnl * (n ** 0.5)) if std_pnl > 0 else 0.0
    else:
        sharpe = 0.0

    # Walk chronologically (trades passed in already sorted by settled_at) to compute a
    # cumulative-pnl peak-to-trough drawdown, expressed as a fraction of running equity.
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    ordered = sorted(
        (t for t in trades if t.pnl is not None and t.settled_at is not None),
        key=lambda t: t.settled_at,
    )
    for t in ordered:
        cumulative += t.pnl
        if cumulative > peak:
            peak = cumulative
        if peak > 0:
            dd = (peak - cumulative) / peak
            max_dd = max(max_dd, dd)

    avg_pnl = sum(pnls) / n

    return {
        "win_rate": round(win_rate, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_pnl_per_trade": round(avg_pnl, 4),
        "num_trades": n,
    }


async def _snapshot_calibration(db: AsyncSession, portfolio: Portfolio, used_xgboost_recent: bool) -> CalibrationSnapshot:
    """Recompute calibration over the trailing 50 settled trades (rolling window) for this
    portfolio mode, plus the Brier score against the recorded ensemble probabilities."""
    result = await db.execute(
        select(Trade)
        .where(Trade.portfolio_id == portfolio.id, Trade.status.in_(["settled_win", "settled_loss"]))
        .order_by(Trade.settled_at.desc())
        .limit(50)
    )
    trades = list(result.scalars())
    stats = _compute_calibration_stats(trades)

    # Brier score: predicted probability of the side actually taken vs. realized outcome (1/0).
    predictions: list[float] = []
    outcomes: list[float] = []
    if trades:
        signal_ids = [t.signal_id for t in trades if t.signal_id]
        sig_result = await db.execute(select(PredictionSignal).where(PredictionSignal.id.in_(signal_ids)))
        signals_by_id = {s.id: s for s in sig_result.scalars()}
        for t in trades:
            sig = signals_by_id.get(t.signal_id)
            if sig is None:
                continue
            predicted_p = sig.final_probability if t.side == "YES" else (1 - sig.final_probability)
            predictions.append(predicted_p)
            outcomes.append(1.0 if t.status == "settled_win" else 0.0)

    brier = calibration.compute_brier_score(predictions, outcomes)

    snapshot = CalibrationSnapshot(
        id=str(uuid.uuid4()),
        mode=portfolio.mode,
        snapshot_at=datetime.utcnow(),
        window="rolling_50",
        win_rate=stats["win_rate"],
        sharpe_ratio=stats["sharpe_ratio"],
        max_drawdown_pct=stats["max_drawdown_pct"],
        profit_factor=stats["profit_factor"],
        brier_score=round(brier, 4),
        avg_pnl_per_trade=stats["avg_pnl_per_trade"],
        num_trades=stats["num_trades"],
        xgboost_active=used_xgboost_recent,
    )
    db.add(snapshot)
    return snapshot


async def run_postmortem(db: AsyncSession, trade: Trade) -> PostMortem:
    market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == trade.market_id))
    market = market_result.scalar_one_or_none()

    signal_result = await db.execute(select(PredictionSignal).where(PredictionSignal.id == trade.signal_id))
    signal = signal_result.scalar_one_or_none()

    outcome = "WIN" if (trade.pnl or 0) > 0 else "LOSS"

    # Context tags for surfacing similar past post-mortems
    edge_pct = signal.edge if signal else None
    gap_pct = None
    if signal and signal.research_brief_id:
        brief_result = await db.execute(select(ResearchBrief).where(ResearchBrief.id == signal.research_brief_id))
        brief = brief_result.scalar_one_or_none()
        if brief:
            gap_pct = brief.gap_pct

    role_agreement_pct = None
    if signal:
        forecast_result = await db.execute(select(ModelForecast).where(ModelForecast.signal_id == signal.id))
        forecasts = list(forecast_result.scalars())
        ok_forecasts = [f for f in forecasts if f.status == "ok"]
        if ok_forecasts:
            bullish_count = sum(1 for f in ok_forecasts if f.probability >= 0.5)
            role_agreement_pct = max(bullish_count, len(ok_forecasts) - bullish_count) / len(ok_forecasts)

    context_tags = context_matcher.extract_context_tags(
        category=market.category if market else "",
        edge_pct=edge_pct,
        gap_pct=gap_pct,
        role_agreement_pct=role_agreement_pct,
        used_xgboost=signal.used_xgboost if signal else None,
        action=signal.action if signal else None,
    )

    pm_result = await db.execute(select(PostMortem))
    existing_postmortems = list(pm_result.scalars())
    scored = sorted(
        ((context_matcher.score_entry(p, context_tags), p) for p in existing_postmortems),
        key=lambda x: x[0], reverse=True,
    )
    similar_past = [p for _, p in scored[:3]]

    lesson = await _build_lesson(trade, market, signal, similar_past)

    postmortem = PostMortem(
        id=str(uuid.uuid4()),
        trade_id=trade.id,
        market_id=trade.market_id,
        outcome=outcome,
        analysis_text=lesson["analysis"],
        failure_category=lesson["failure_category"],
        lesson_title=lesson["lesson_title"],
        lesson_body=lesson["lesson_body"],
        importance=lesson["importance"],
        similar_past_trade_ids=[p.trade_id for p in similar_past],
        created_at=datetime.utcnow(),
    )
    # PostMortem doesn't have its own `.tags` column (context_matcher.score_entry() reads
    # entry.tags); reuse failure_category + a category tag as an ad-hoc tags attribute isn't
    # persisted on this model — context tags are recomputed fresh each time from the trade,
    # so no tags column is needed on PostMortem itself.
    db.add(postmortem)

    if lesson["importance"] >= KNOWLEDGE_IMPORTANCE_THRESHOLD:
        kb = KnowledgeEntry(
            id=str(uuid.uuid4()),
            category="postmortem",
            market=market.category if market else "all",
            title=lesson["lesson_title"],
            content=lesson["lesson_body"],
            source="postmortem_agent",
            importance=lesson["importance"],
            tags=context_tags,
            created_at=datetime.utcnow(),
        )
        db.add(kb)

    portfolio_result = await db.execute(select(Portfolio).where(Portfolio.id == trade.portfolio_id))
    portfolio = portfolio_result.scalar_one_or_none()
    if portfolio:
        await _snapshot_calibration(db, portfolio, used_xgboost_recent=bool(signal and signal.used_xgboost))

    await db.commit()
    await db.refresh(postmortem)

    # Fire-and-forget XGBoost retrain every xgboost_retrain_interval settlements (per mode,
    # in-process counter — sufficient for a single-backend-instance deployment).
    mode = trade.mode
    _settlement_counts[mode] = _settlement_counts.get(mode, 0) + 1
    if _settlement_counts[mode] >= settings.xgboost_retrain_interval:
        _settlement_counts[mode] = 0
        try:
            import asyncio
            asyncio.create_task(_retrain_in_background())
        except Exception as e:
            log.warning("xgboost_retrain_schedule_failed", error=str(e))

    await redis_client.publish("postmortem:new", {
        "id": postmortem.id,
        "trade_id": postmortem.trade_id,
        "market_id": postmortem.market_id,
        "outcome": postmortem.outcome,
        "analysis_text": postmortem.analysis_text,
        "failure_category": postmortem.failure_category,
        "lesson_title": postmortem.lesson_title,
        "lesson_body": postmortem.lesson_body,
        "importance": postmortem.importance,
        "similar_past_trade_ids": postmortem.similar_past_trade_ids,
        "created_at": postmortem.created_at.isoformat(),
    })
    log.info("postmortem_complete", trade_id=trade.id, outcome=outcome,
             failure_category=postmortem.failure_category, importance=postmortem.importance)

    return postmortem


async def _retrain_in_background() -> None:
    """Runs in its own DB session since it's scheduled via asyncio.create_task() outside
    the caller's request-scoped session lifetime."""
    from app.db.session import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            await calibration.train_or_update_model(db)
    except Exception as e:
        log.error("xgboost_background_retrain_failed", error=str(e))
