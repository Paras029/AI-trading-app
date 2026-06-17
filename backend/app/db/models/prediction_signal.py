import uuid
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class PredictionSignal(Base):
    """Aggregated output of the Prediction Agent (ensemble + optional XGBoost blend).
    Replaces the old AISignal model."""

    __tablename__ = "prediction_signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    market_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_markets.id"), index=True)
    research_brief_id: Mapped[str | None] = mapped_column(String, ForeignKey("research_briefs.id"), nullable=True)
    ensemble_probability: Mapped[float] = mapped_column(Float, default=0.0)
    final_probability: Mapped[float] = mapped_column(Float, default=0.0)
    market_price: Mapped[float] = mapped_column(Float, default=0.0)
    edge: Mapped[float] = mapped_column(Float, default=0.0)
    expected_value: Mapped[float] = mapped_column(Float, default=0.0)
    z_score: Mapped[float] = mapped_column(Float, default=0.0)
    used_xgboost: Mapped[bool] = mapped_column(Boolean, default=False)
    feature_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[str] = mapped_column(String, default="SKIP")  # BUY_YES | BUY_NO | WATCH | SKIP
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
