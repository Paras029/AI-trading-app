from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Lesson
from app.schemas.common import LessonOut

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


@router.get("")
async def get_lessons(market: str = "crypto", db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Lesson).where(Lesson.market == market).order_by(Lesson.importance.desc(), Lesson.created_at.desc())
    )
    return [LessonOut.model_validate(l).model_dump() for l in result.scalars()]
