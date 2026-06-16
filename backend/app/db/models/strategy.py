import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
import enum


class StrategyStatus(str, enum.Enum):
    active = "active"
    candidate = "candidate"
    retired = "retired"


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, index=True)
    market: Mapped[str] = mapped_column(String, default="crypto")
    status: Mapped[str] = mapped_column(SAEnum(StrategyStatus), default=StrategyStatus.candidate)
    description: Mapped[str] = mapped_column(Text, default="")
    # Statistical metrics
    exp_r: Mapped[float] = mapped_column(Float, default=0.0)       # Expected R-multiple
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    num_trades: Mapped[int] = mapped_column(Integer, default=0)
    # Activation gates: exp_r > 0, profit_factor > 1.0, sharpe > 0.5
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
