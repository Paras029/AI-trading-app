from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Generation
from app.schemas.common import GenerationOut

router = APIRouter(prefix="/api/evolution", tags=["evolution"])


@router.get("")
async def get_generations(market: str = "crypto", db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Generation).where(Generation.market == market).order_by(Generation.number)
    )
    return [GenerationOut.model_validate(g).model_dump() for g in result.scalars()]
