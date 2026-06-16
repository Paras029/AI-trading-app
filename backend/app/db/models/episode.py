import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
import enum


class EpisodeOutcome(str, enum.Enum):
    running = "running"
    goal = "goal"
    blowup = "blowup"


class Market(str, enum.Enum):
    crypto = "crypto"
    us_stocks = "us_stocks"
    india_stocks = "india_stocks"
    forex = "forex"


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    market: Mapped[str] = mapped_column(SAEnum(Market), default=Market.crypto)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    start_equity: Mapped[float] = mapped_column(Float, default=100.0)
    goal_equity: Mapped[float] = mapped_column(Float, default=500.0)
    current_equity: Mapped[float] = mapped_column(Float, default=100.0)
    peak_equity: Mapped[float] = mapped_column(Float, default=100.0)
    num_trades: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(SAEnum(EpisodeOutcome), default=EpisodeOutcome.running)
    start_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
