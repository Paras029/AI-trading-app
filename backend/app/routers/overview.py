from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.db.models import Episode, Position, Generation
from app.db.models.episode import EpisodeOutcome
from app.schemas.common import EpisodeOut, PositionOut
from app.core import redis_client

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("")
async def get_overview(market: str = "crypto", db: AsyncSession = Depends(get_db)):
    # Active episode
    result = await db.execute(
        select(Episode).where(
            Episode.market == market,
            Episode.outcome == EpisodeOutcome.running,
        ).order_by(Episode.start_at.desc()).limit(1)
    )
    episode = result.scalar_one_or_none()

    # Open positions
    positions = []
    if episode:
        pos_result = await db.execute(
            select(Position).where(Position.episode_id == episode.id)
        )
        positions = pos_result.scalars().all()

    # Latest generation notification
    gen_result = await db.execute(
        select(Generation).where(Generation.market == market).order_by(Generation.created_at.desc()).limit(1)
    )
    latest_gen = gen_result.scalar_one_or_none()

    # Equity history from all finished episodes
    finished_result = await db.execute(
        select(Episode).where(Episode.market == market, Episode.outcome != EpisodeOutcome.running)
        .order_by(Episode.start_at)
    )
    finished = finished_result.scalars().all()

    return {
        "episode": EpisodeOut.model_validate(episode).model_dump() if episode else None,
        "positions": [PositionOut.model_validate(p).model_dump() for p in positions],
        "latest_generation": latest_gen.number if latest_gen else 1,
        "notification": latest_gen.summary_text[:200] if latest_gen else None,
        "finished_episodes_count": len(finished),
    }
