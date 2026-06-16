import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class AISignal(Base):
    __tablename__ = "ai_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    market: Mapped[str] = mapped_column(String, default="crypto")
    symbol: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)           # BUY | SELL | HOLD
    confidence: Mapped[float] = mapped_column(Float)      # 0.0 – 1.0
    reasoning: Mapped[str] = mapped_column(Text)
    risk_note: Mapped[str] = mapped_column(Text, default="")
    indicators_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    price_at_signal: Mapped[float] = mapped_column(Float)
    episode_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
