"""
GET /api/dashboard — single aggregate snapshot for the Overview page: portfolio ledger,
trailing calibration stats (win-rate/Sharpe/Brier), current pipeline backlog counts, and
today's realized P&L. Mirrors the same counts the orchestrator publishes on
'pipeline:status' so a fresh page load doesn't have to wait for the next WS tick.
"""
from datetime import datetime, timedelta
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.db.models import Portfolio, PredictionMarket, Trade, CalibrationSnapshot
from app.core import redis_client
from app.schemas.common import DashboardData, PipelineStatusCounts, PortfolioOut

log = structlog.get_logger()
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardData)
async def get_dashboard(
    mode: str = Query(default="paper"),
    db: AsyncSession = Depends(get_db),
):
    bot_config = await redis_client.get_bot_config()

    pf_result = await db.execute(select(Portfolio).where(Portfolio.mode == mode))
    portfolio = pf_result.scalar_one_or_none()

    snap_result = await db.execute(
        select(CalibrationSnapshot)
        .where(CalibrationSnapshot.mode == mode)
        .order_by(CalibrationSnapshot.snapshot_at.desc())
        .limit(1)
    )
    snapshot = snap_result.scalar_one_or_none()

    win_rate = snapshot.win_rate if snapshot else 0.0
    sharpe_ratio = snapshot.sharpe_ratio if snapshot else 0.0
    brier_score = snapshot.brier_score if snapshot else 0.0

    active_positions = 0
    if portfolio:
        active_result = await db.execute(
            select(func.count(Trade.id)).where(Trade.portfolio_id == portfolio.id, Trade.status == "open")
        )
        active_positions = int(active_result.scalar() or 0)

    position_limit = int(bot_config.get("max_concurrent_positions", 8))

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

    running = await redis_client.is_bot_running()
    paused = await redis_client.is_bot_paused()
    system_status = "stopped" if not running else ("paused" if paused else "operational")

    pnl_today = 0.0
    if portfolio:
        since = datetime.utcnow() - timedelta(hours=24)
        pnl_result = await db.execute(
            select(func.sum(Trade.pnl)).where(
                Trade.portfolio_id == portfolio.id,
                Trade.settled_at >= since,
                Trade.status.in_(["settled_win", "settled_loss"]),
            )
        )
        pnl_today = float(pnl_result.scalar() or 0.0)

    return DashboardData(
        portfolio=PortfolioOut.model_validate(portfolio) if portfolio else None,
        win_rate=win_rate,
        sharpe_ratio=sharpe_ratio,
        brier_score=brier_score,
        active_positions=active_positions,
        position_limit=position_limit,
        pipeline_status=PipelineStatusCounts(
            scanner=int(scanner_count),
            research=int(research_count),
            prediction=int(prediction_count),
            risk=int(risk_count),
            settlement=int(settlement_count),
        ),
        system_status=system_status,
        pnl_today=round(pnl_today, 4),
    )
