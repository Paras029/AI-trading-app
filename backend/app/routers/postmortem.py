"""
Post-mortem API — replaces the old /api/lessons. Read-only access to PostMortem rows
written by the Post-Mortem Agent after each trade settles, plus a failure-category
breakdown aggregation for the Lessons page's chart.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.session import get_db
from app.db.models import PostMortem
from app.schemas.common import PostMortemOut, FailureBreakdownEntry

router = APIRouter(prefix="/api/postmortems", tags=["postmortems"])


@router.get("", response_model=list[PostMortemOut])
async def list_postmortems(
    outcome: str | None = Query(default=None),
    min_importance: int = Query(default=0, ge=0, le=10),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(PostMortem).where(PostMortem.importance >= min_importance)
    if outcome:
        q = q.where(PostMortem.outcome == outcome)
    q = q.order_by(PostMortem.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [PostMortemOut.model_validate(p) for p in result.scalars()]


@router.get("/{postmortem_id}", response_model=PostMortemOut)
async def get_postmortem(postmortem_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PostMortem).where(PostMortem.id == postmortem_id))
    pm = result.scalar_one_or_none()
    if pm is None:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    return PostMortemOut.model_validate(pm)


@router.get("/breakdown/failure-categories", response_model=list[FailureBreakdownEntry])
async def get_failure_breakdown(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PostMortem.failure_category, func.count(PostMortem.id))
        .where(PostMortem.outcome == "LOSS", PostMortem.failure_category.is_not(None))
        .group_by(PostMortem.failure_category)
    )
    rows = result.all()
    total = sum(count for _, count in rows)
    if total == 0:
        return []
    return [
        FailureBreakdownEntry(
            failure_category=category,
            count=count,
            pct=round((count / total) * 100, 2),
        )
        for category, count in rows
    ]
