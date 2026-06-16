from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Position, Episode
from app.db.models.episode import EpisodeOutcome
from app.schemas.common import PositionOut

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
async def get_positions(market: str = "crypto", db: AsyncSession = Depends(get_db)):
    ep_result = await db.execute(
        select(Episode).where(Episode.market == market, Episode.outcome == EpisodeOutcome.running)
        .order_by(Episode.start_at.desc()).limit(1)
    )
    episode = ep_result.scalar_one_or_none()
    if not episode:
        return []

    result = await db.execute(select(Position).where(Position.episode_id == episode.id))
    return [PositionOut.model_validate(p).model_dump() for p in result.scalars()]
