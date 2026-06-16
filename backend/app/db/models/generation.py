import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    market: Mapped[str] = mapped_column(String, default="crypto")
    number: Mapped[int] = mapped_column(Integer)
    after_episode_id: Mapped[str] = mapped_column(String)
    summary_text: Mapped[str] = mapped_column(Text)
    kelly_fraction: Mapped[float] = mapped_column(Float, default=0.25)
    max_leverage: Mapped[int] = mapped_column(Integer, default=6)
    lessons_count: Mapped[int] = mapped_column(Integer, default=0)
    promoted_strategies: Mapped[str] = mapped_column(String, default="")   # comma-separated names
    retired_strategies: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
