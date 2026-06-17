from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Trade, PredictionSignal, ModelForecast, RiskGateCheck
from app.schemas.common import TradeOut, PredictionSignalOut, ModelForecastOut, RiskGateCheckOut
from app.services.execution.polymarket_live import ExecutionBlockedError

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("", response_model=list[TradeOut])
async def get_trades(
    mode: str = "paper",
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    open_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(Trade).where(Trade.mode == mode)
    if open_only:
        q = q.where(Trade.status == "open")
    elif status:
        q = q.where(Trade.status == status)
    q = q.order_by(Trade.opened_at.desc()).limit(limit)
    result = await db.execute(q)
    return [TradeOut.model_validate(t) for t in result.scalars()]


@router.get("/{trade_id}")
async def get_trade_detail(trade_id: str, db: AsyncSession = Depends(get_db)):
    """TradeDetail per frontend types.ts — Trade plus nested signal/forecasts/gate_checks."""
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")

    signal_result = await db.execute(select(PredictionSignal).where(PredictionSignal.id == trade.signal_id))
    signal = signal_result.scalar_one_or_none()

    forecasts: list[ModelForecast] = []
    gate_checks: list[RiskGateCheck] = []
    if signal:
        forecast_result = await db.execute(select(ModelForecast).where(ModelForecast.signal_id == signal.id))
        forecasts = list(forecast_result.scalars())
        gate_result = await db.execute(
            select(RiskGateCheck).where(RiskGateCheck.signal_id == signal.id).order_by(RiskGateCheck.sequence.asc())
        )
        gate_checks = list(gate_result.scalars())

    return {
        **TradeOut.model_validate(trade).model_dump(),
        "signal": PredictionSignalOut.model_validate(signal).model_dump() if signal else None,
        "forecasts": [ModelForecastOut.model_validate(f).model_dump() for f in forecasts],
        "gate_checks": [RiskGateCheckOut.model_validate(c).model_dump() for c in gate_checks],
    }


@router.post("/{trade_id}/close")
async def close_trade(trade_id: str, db: AsyncSession = Depends(get_db)):
    """Closes ONE open trade early, independent of bot running/paused state."""
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status != "open":
        raise HTTPException(status_code=400, detail=f"Trade is not open (status={trade.status})")

    try:
        if trade.mode == "paper":
            from app.services.execution import paper
            closed = await paper.close_trade_early(db, trade)
        else:
            from app.services.execution import polymarket_live
            closed = await polymarket_live.close_position(db, trade)
    except ExecutionBlockedError as e:
        raise HTTPException(status_code=400, detail=f"Live close blocked: {e}")

    return TradeOut.model_validate(closed)


@router.post("/close-all")
async def close_all_trades(mode: str = Query(default="paper"), db: AsyncSession = Depends(get_db)):
    """Closes every open trade for the given mode. Sequential (not gathered) so failures
    are isolated and reported per-trade. Independent of bot running/paused state."""
    result = await db.execute(select(Trade).where(Trade.mode == mode, Trade.status == "open"))
    open_trades = list(result.scalars())

    results = []
    for trade in open_trades:
        try:
            if trade.mode == "paper":
                from app.services.execution import paper
                closed = await paper.close_trade_early(db, trade)
            else:
                from app.services.execution import polymarket_live
                closed = await polymarket_live.close_position(db, trade)
            results.append({"trade_id": trade.id, "status": "closed", "pnl": closed.pnl})
        except Exception as e:
            results.append({"trade_id": trade.id, "status": "failed", "error": str(e)[:300]})

    return {
        "mode": mode,
        "total": len(open_trades),
        "closed": sum(1 for r in results if r["status"] == "closed"),
        "results": results,
    }
