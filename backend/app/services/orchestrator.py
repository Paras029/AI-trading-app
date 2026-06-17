"""
Orchestrator — wires the 5-stage pipeline into independent async loops, each with its own
interval and its own per-iteration AsyncSessionLocal() session (never one long-lived session
shared across iterations). Errors in one item never block the rest of the batch
(asyncio.gather(..., return_exceptions=True)).

Stages:
  1. Scanner    (scan_interval_seconds, default 300s) — active -> scanned/rejected
  2. Research   (60s)                                  — scanned -> researched
  3. Prediction (60s)                                  — researched -> signaled
  4. Risk       (30s)                                   — signaled -> traded/rejected
  5. Settlement (600s)                                  — open Trade -> settled_win/settled_loss

Also publishes a periodic 'pipeline:status' snapshot the frontend dashboard renders directly
(PipelineStatusCounts + system_status, flat — not nested).
"""
import asyncio
import uuid
from datetime import datetime
import structlog
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.db.models import (
    PredictionMarket, ResearchBrief, PredictionSignal, Trade, Portfolio,
)
from app.core import redis_client
from app.services.agents import scanner_agent, research_agent, risk_agent
from app.services.prediction import ensemble, features, calibration
from app.services.execution import paper
from app.services.market_data import polymarket

log = structlog.get_logger()

RESEARCH_BATCH_SIZE = 5
PREDICTION_BATCH_SIZE = 5
RISK_BATCH_SIZE = 10
SETTLEMENT_BATCH_SIZE = 25

_tasks: list[asyncio.Task] = []


async def _sleep_with_jitter(seconds: float) -> None:
    await asyncio.sleep(seconds)


# ── Stage 1: Scanner ─────────────────────────────────────────────────────────

async def _scanner_pass() -> None:
    bot_config = await redis_client.get_bot_config()
    filters = {
        "categories": bot_config.get("scanner_categories", scanner_agent.DEFAULT_FILTERS["categories"]),
        "min_volume": bot_config.get("scanner_min_volume", scanner_agent.DEFAULT_FILTERS["min_volume"]),
        "max_expiry_days": bot_config.get("scanner_max_expiry_days", scanner_agent.DEFAULT_FILTERS["max_expiry_days"]),
        "min_edge_pct": bot_config.get("scanner_min_edge_pct", scanner_agent.DEFAULT_FILTERS["min_edge_pct"]),
    }
    async with AsyncSessionLocal() as db:
        try:
            await scanner_agent.scan_markets(db, filters)
        except Exception as e:
            log.error("scanner_pass_failed", error=str(e))


async def run_scanner_loop() -> None:
    log.info("scanner_loop_started")
    while True:
        try:
            await _scanner_pass()
        except Exception as e:
            log.error("scanner_loop_error", error=str(e))
        bot_config = await redis_client.get_bot_config()
        interval = float(bot_config.get("scan_interval_seconds", 300))
        await _sleep_with_jitter(interval)


# ── Stage 2: Research ────────────────────────────────────────────────────────

async def _research_one(market_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == market_id))
        market = result.scalar_one_or_none()
        if market is None or market.status != "scanned":
            return
        await research_agent.research_market(db, market)


async def run_research_loop() -> None:
    log.info("research_loop_started")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(PredictionMarket.id)
                    .where(PredictionMarket.status == "scanned")
                    .order_by(PredictionMarket.last_scanned_at.asc())
                    .limit(RESEARCH_BATCH_SIZE)
                )
                market_ids = [r[0] for r in result.all()]

            if market_ids:
                await asyncio.gather(*[_research_one(mid) for mid in market_ids], return_exceptions=True)
        except Exception as e:
            log.error("research_loop_error", error=str(e))
        await _sleep_with_jitter(60)


# ── Stage 3: Prediction ───────────────────────────────────────────────────────

async def _predict_one(market_id: str) -> None:
    async with AsyncSessionLocal() as db:
        market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == market_id))
        market = market_result.scalar_one_or_none()
        if market is None or market.status != "researched":
            return

        brief_result = await db.execute(
            select(ResearchBrief).where(ResearchBrief.market_id == market.id)
            .order_by(ResearchBrief.created_at.desc()).limit(1)
        )
        brief = brief_result.scalar_one_or_none()

        forecasts = await ensemble.run_ensemble(db, market, brief)
        ensemble_prob = ensemble.aggregate(forecasts)

        forecast_dicts = [
            {"probability": f.probability, "status": f.status, "weight_applied": f.weight_applied}
            for f in forecasts
        ]
        orderbook = await polymarket.fetch_orderbook(market.yes_token_id) if market.yes_token_id else {"bids": [], "asks": []}
        spread = polymarket.compute_spread(orderbook)
        market._spread = spread  # transient attribute consumed by build_feature_vector only

        feature_vector = features.build_feature_vector(market, brief, forecast_dicts)
        final_prob, used_xgboost = await ensemble.blend_with_xgboost(db, ensemble_prob, feature_vector)

        bot_config = await redis_client.get_bot_config()
        edge_threshold = float(bot_config.get("min_edge_pct", 0.05))
        signal_calc = ensemble.compute_signal(final_prob, market.current_yes_price, edge_threshold)

        # z_score: how many ensemble-forecast standard deviations the final probability
        # sits from the market-implied probability — a quick calibration sanity signal.
        ok_probs = [f.probability for f in forecasts if f.status == "ok" and f.probability is not None]
        if len(ok_probs) >= 2:
            mean_p = sum(ok_probs) / len(ok_probs)
            std_p = (sum((p - mean_p) ** 2 for p in ok_probs) / len(ok_probs)) ** 0.5
            z_score = (final_prob - market.current_yes_price) / std_p if std_p > 0 else 0.0
        else:
            z_score = 0.0

        signal = PredictionSignal(
            id=str(uuid.uuid4()),
            market_id=market.id,
            research_brief_id=brief.id if brief else None,
            ensemble_probability=round(ensemble_prob, 4),
            final_probability=round(final_prob, 4),
            market_price=market.current_yes_price,
            edge=signal_calc["edge"],
            expected_value=signal_calc["expected_value"],
            z_score=round(z_score, 4),
            used_xgboost=used_xgboost,
            feature_snapshot=feature_vector,
            action=signal_calc["action"],
            created_at=datetime.utcnow(),
        )
        db.add(signal)

        for f in forecasts:
            f.signal_id = signal.id

        market.status = "signaled"
        await db.commit()
        await db.refresh(signal)

        await redis_client.publish("prediction:signal", {
            "id": signal.id,
            "market_id": signal.market_id,
            "ensemble_probability": signal.ensemble_probability,
            "final_probability": signal.final_probability,
            "market_price": signal.market_price,
            "edge": signal.edge,
            "expected_value": signal.expected_value,
            "z_score": signal.z_score,
            "used_xgboost": signal.used_xgboost,
            "action": signal.action,
            "created_at": signal.created_at.isoformat(),
        })

        if signal.action in ("BUY_YES", "BUY_NO"):
            await redis_client.publish("risk:queued", {"signal_id": signal.id, "market_id": market.id})


async def run_prediction_loop() -> None:
    log.info("prediction_loop_started")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(PredictionMarket.id)
                    .where(PredictionMarket.status == "researched")
                    .limit(PREDICTION_BATCH_SIZE)
                )
                market_ids = [r[0] for r in result.all()]

            if market_ids:
                await asyncio.gather(*[_predict_one(mid) for mid in market_ids], return_exceptions=True)
        except Exception as e:
            log.error("prediction_loop_error", error=str(e))
        await _sleep_with_jitter(60)


# ── Stage 4: Risk ─────────────────────────────────────────────────────────────

async def _risk_check_one(signal_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PredictionSignal).where(PredictionSignal.id == signal_id))
        signal = result.scalar_one_or_none()
        if signal is None:
            return
        market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == signal.market_id))
        market = market_result.scalar_one_or_none()
        if market is None or market.status != "signaled":
            return
        if signal.action not in ("BUY_YES", "BUY_NO"):
            # WATCH/SKIP signals never reach the risk stage — mark resolved either way so
            # the market doesn't loop forever in 'signaled'.
            market.status = "rejected" if signal.action == "SKIP" else "active"
            await db.commit()
            return
        await risk_agent.run_risk_check(db, signal)


async def run_risk_loop() -> None:
    log.info("risk_loop_started")
    while True:
        try:
            paused = await redis_client.is_bot_paused()
            if paused:
                log.debug("risk_loop_skipped_bot_paused")
            else:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(PredictionSignal.id)
                        .join(PredictionMarket, PredictionSignal.market_id == PredictionMarket.id)
                        .where(PredictionMarket.status == "signaled")
                        .order_by(PredictionSignal.created_at.asc())
                        .limit(RISK_BATCH_SIZE)
                    )
                    signal_ids = [r[0] for r in result.all()]

                if signal_ids:
                    await asyncio.gather(*[_risk_check_one(sid) for sid in signal_ids], return_exceptions=True)
        except Exception as e:
            log.error("risk_loop_error", error=str(e))
        await _sleep_with_jitter(30)


# ── Stage 5: Settlement ────────────────────────────────────────────────────────

async def _settle_one(trade_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Trade).where(Trade.id == trade_id))
        trade = result.scalar_one_or_none()
        if trade is None or trade.status != "open":
            return
        market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == trade.market_id))
        market = market_result.scalar_one_or_none()
        if market is None or not market.resolved_outcome:
            return
        await paper.settle_trade(db, trade, market.resolved_outcome)
        if market.status != "settled":
            market.status = "settled"
            await db.commit()


async def run_settlement_loop() -> None:
    log.info("settlement_loop_started")
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Trade.id).where(Trade.status == "open").limit(SETTLEMENT_BATCH_SIZE)
                )
                trade_ids = [r[0] for r in result.all()]

            if trade_ids:
                # Refresh resolved_outcome from Polymarket before checking each trade's market.
                async with AsyncSessionLocal() as db:
                    market_result = await db.execute(
                        select(PredictionMarket)
                        .join(Trade, Trade.market_id == PredictionMarket.id)
                        .where(Trade.id.in_(trade_ids), PredictionMarket.status != "settled")
                    )
                    markets = list({m.id: m for m in market_result.scalars()}.values())
                    for market in markets:
                        try:
                            resolved = await polymarket.fetch_market_resolution(market.polymarket_condition_id)
                        except Exception as e:
                            log.warning("settlement_resolution_check_failed", market_id=market.id, error=str(e))
                            resolved = None
                        if resolved:
                            market.resolved_outcome = resolved
                            market.resolved_at = datetime.utcnow()
                    await db.commit()

                await asyncio.gather(*[_settle_one(tid) for tid in trade_ids], return_exceptions=True)
        except Exception as e:
            log.error("settlement_loop_error", error=str(e))
        await _sleep_with_jitter(600)


# ── Pipeline status broadcaster ────────────────────────────────────────────────

async def _pipeline_status_pass() -> None:
    async with AsyncSessionLocal() as db:
        scanner_count = (await db.execute(
            select(func.count(PredictionMarket.id)).where(PredictionMarket.status == "active")
        )).scalar() or 0
        research_count = (await db.execute(
            select(func.count(PredictionMarket.id)).where(PredictionMarket.status == "scanned")
        )).scalar() or 0
        prediction_count = (await db.execute(
            select(func.count(PredictionMarket.id)).where(PredictionMarket.status == "researched")
        )).scalar() or 0
        risk_count = (await db.execute(
            select(func.count(PredictionMarket.id)).where(PredictionMarket.status == "signaled")
        )).scalar() or 0
        settlement_count = (await db.execute(
            select(func.count(Trade.id)).where(Trade.status == "open")
        )).scalar() or 0

    paused = await redis_client.is_bot_paused()
    system_status = "paused" if paused else "operational"

    await redis_client.publish("pipeline:status", {
        "scanner": int(scanner_count),
        "research": int(research_count),
        "prediction": int(prediction_count),
        "risk": int(risk_count),
        "settlement": int(settlement_count),
        "system_status": system_status,
    })


async def run_pipeline_status_loop() -> None:
    log.info("pipeline_status_loop_started")
    while True:
        try:
            await _pipeline_status_pass()
        except Exception as e:
            log.error("pipeline_status_loop_error", error=str(e))
        await _sleep_with_jitter(15)


# ── Lifecycle ──────────────────────────────────────────────────────────────────

async def start_all() -> None:
    log.info("orchestrator_starting")
    _tasks.extend([
        asyncio.create_task(run_scanner_loop(), name="scanner_loop"),
        asyncio.create_task(run_research_loop(), name="research_loop"),
        asyncio.create_task(run_prediction_loop(), name="prediction_loop"),
        asyncio.create_task(run_risk_loop(), name="risk_loop"),
        asyncio.create_task(run_settlement_loop(), name="settlement_loop"),
        asyncio.create_task(run_pipeline_status_loop(), name="pipeline_status_loop"),
    ])
    log.info("orchestrator_started", task_count=len(_tasks))


async def stop_all() -> None:
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    log.info("orchestrator_stopped")
