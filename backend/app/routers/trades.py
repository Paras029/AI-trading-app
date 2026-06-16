from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Trade
from app.schemas.common import TradeOut

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
async def get_trades(
    market: str = "crypto",
    limit: int = Query(default=50, le=200),
    open_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(Trade).where(Trade.market == market)
    if open_only:
        q = q.where(Trade.is_open == True)
    q = q.order_by(Trade.opened_at.desc()).limit(limit)
    result = await db.execute(q)
    return [TradeOut.model_validate(t).model_dump() for t in result.scalars()]
