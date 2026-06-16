from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Episode
from app.schemas.common import EpisodeOut

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


@router.get("")
async def get_episodes(market: str = "crypto", db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Episode).where(Episode.market == market).order_by(Episode.start_at)
    )
    return [EpisodeOut.model_validate(e).model_dump() for e in result.scalars()]
