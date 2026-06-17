"""Research API — read-only access to ResearchBrief rows written by the Research Agent."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import ResearchBrief
from app.schemas.common import ResearchBriefOut

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/briefs", response_model=list[ResearchBriefOut])
async def list_briefs(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResearchBrief).order_by(ResearchBrief.created_at.desc()).limit(limit)
    )
    return [ResearchBriefOut.model_validate(b) for b in result.scalars()]


@router.get("/briefs/{market_id}", response_model=list[ResearchBriefOut])
async def get_briefs_for_market(
    market_id: str,
    limit: int = Query(default=10, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ResearchBrief)
        .where(ResearchBrief.market_id == market_id)
        .order_by(ResearchBrief.created_at.desc())
        .limit(limit)
    )
    briefs = list(result.scalars())
    if not briefs:
        raise HTTPException(status_code=404, detail="No research briefs found for this market")
    return [ResearchBriefOut.model_validate(b) for b in briefs]
