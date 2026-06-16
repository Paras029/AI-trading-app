from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Strategy
from app.schemas.common import StrategyOut

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("")
async def get_strategies(market: str = "crypto", db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Strategy).where(Strategy.market == market).order_by(Strategy.status, Strategy.exp_r.desc())
    )
    return [StrategyOut.model_validate(s).model_dump() for s in result.scalars()]
