import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class ModelForecast(Base):
    """One row per ensemble role call per prediction pass (the fan-out across
    primary_forecaster/news_analyst/bull_advocate/bear_advocate/risk_contrarian)."""

    __tablename__ = "model_forecasts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    market_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_markets.id"), index=True)
    signal_id: Mapped[str | None] = mapped_column(String, ForeignKey("prediction_signals.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String, index=True)  # primary_forecaster | news_analyst | bull_advocate | bear_advocate | risk_contrarian
    provider: Mapped[str] = mapped_column(String)          # anthropic | google | openai | deepseek
    model: Mapped[str] = mapped_column(String)
    probability: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    weight_configured: Mapped[float] = mapped_column(Float, default=0.0)
    weight_applied: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="ok")  # ok | skipped_no_key | error | timeout
    error_detail: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
