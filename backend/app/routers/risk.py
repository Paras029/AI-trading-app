"""Risk API — read-only access to RiskGateCheck history plus current gate thresholds
(sourced from Redis bot:config, falling back to RISK_GATE_DEFAULTS)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import RiskGateCheck
from app.core import redis_client
from app.config import RISK_GATE_DEFAULTS
from app.schemas.common import RiskGateCheckOut

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/gate-checks", response_model=list[RiskGateCheckOut])
async def list_gate_checks(
    signal_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(RiskGateCheck)
    if signal_id:
        q = q.where(RiskGateCheck.signal_id == signal_id)
    q = q.order_by(RiskGateCheck.checked_at.desc()).limit(limit)
    result = await db.execute(q)
    return [RiskGateCheckOut.model_validate(c) for c in result.scalars()]


@router.get("/gate-checks/{signal_id}", response_model=list[RiskGateCheckOut])
async def get_gate_checks_for_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RiskGateCheck)
        .where(RiskGateCheck.signal_id == signal_id)
        .order_by(RiskGateCheck.sequence.asc())
    )
    return [RiskGateCheckOut.model_validate(c) for c in result.scalars()]


@router.get("/thresholds")
async def get_thresholds():
    bot_config = await redis_client.get_bot_config()
    return {key: bot_config.get(key, default) for key, default in RISK_GATE_DEFAULTS.items()}
