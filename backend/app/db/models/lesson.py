import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    episode_id: Mapped[str] = mapped_column(String, index=True)
    generation_id: Mapped[str] = mapped_column(String, index=True)
    market: Mapped[str] = mapped_column(String, default="crypto")
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    # Market regime when this lesson was learned
    market_regime: Mapped[str] = mapped_column(String, default="unknown")
    # Importance score 1-10: blow-ups skew toward 10
    importance: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
