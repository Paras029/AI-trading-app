"""Prediction API — read-only access to PredictionSignal rows + their per-role
ModelForecast breakdown, and the latest CalibrationSnapshot / XGBoost cold-start status."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.config import settings
from app.db.session import get_db
from app.db.models import PredictionSignal, ModelForecast, CalibrationSnapshot, Trade
from app.schemas.common import PredictionSignalOut, ModelForecastOut, CalibrationSnapshotOut

router = APIRouter(prefix="/api/prediction", tags=["prediction"])


@router.get("/signals", response_model=list[PredictionSignalOut])
async def list_signals(
    limit: int = Query(default=50, le=200),
    action: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    q = select(PredictionSignal)
    if action:
        q = q.where(PredictionSignal.action == action)
    q = q.order_by(PredictionSignal.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [PredictionSignalOut.model_validate(s) for s in result.scalars()]


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PredictionSignal).where(PredictionSignal.id == signal_id))
    signal = result.scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    forecast_result = await db.execute(
        select(ModelForecast).where(ModelForecast.signal_id == signal_id)
    )
    forecasts = list(forecast_result.scalars())

    return {
        **PredictionSignalOut.model_validate(signal).model_dump(),
        "forecasts": [ModelForecastOut.model_validate(f).model_dump() for f in forecasts],
    }


@router.get("/calibration", response_model=CalibrationSnapshotOut | None)
async def get_calibration(
    mode: str = Query(default="paper"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CalibrationSnapshot)
        .where(CalibrationSnapshot.mode == mode)
        .order_by(CalibrationSnapshot.snapshot_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    return CalibrationSnapshotOut.model_validate(snapshot) if snapshot else None


@router.get("/calibration/status")
async def get_calibration_status(
    mode: str = Query(default="paper"),
    db: AsyncSession = Depends(get_db),
):
    """Cold-start status: how many settled trades exist for this mode vs.
    xgboost_min_samples needed before the blend activates."""
    settled_count_result = await db.execute(
        select(func.count(Trade.id)).where(
            Trade.mode == mode, Trade.status.in_(["settled_win", "settled_loss"])
        )
    )
    settled_trade_count = int(settled_count_result.scalar() or 0)

    snap_result = await db.execute(
        select(CalibrationSnapshot)
        .where(CalibrationSnapshot.mode == mode)
        .order_by(CalibrationSnapshot.snapshot_at.desc())
        .limit(1)
    )
    snapshot = snap_result.scalar_one_or_none()

    return {
        "snapshot": CalibrationSnapshotOut.model_validate(snapshot).model_dump() if snapshot else None,
        "xgboost_active": bool(snapshot.xgboost_active) if snapshot else False,
        "xgboost_min_samples": settings.xgboost_min_samples,
        "settled_trade_count": settled_trade_count,
    }
