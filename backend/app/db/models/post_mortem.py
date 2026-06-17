import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class PostMortem(Base):
    """Post-trade analysis written by Claude after a trade settles. Replaces Lesson,
    reshaped around a single trade settlement + failure-category classification."""

    __tablename__ = "post_mortems"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trade_id: Mapped[str] = mapped_column(String, ForeignKey("trades.id"), unique=True, index=True)
    market_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_markets.id"), index=True)
    outcome: Mapped[str] = mapped_column(String)  # WIN | LOSS
    analysis_text: Mapped[str] = mapped_column(Text, default="")
    # null if WIN; else bad_prediction | bad_timing | external_shock | bad_execution |
    # overweighted_sentiment | model_overconfidence
    failure_category: Mapped[str | None] = mapped_column(String, nullable=True)
    lesson_title: Mapped[str] = mapped_column(String, default="")
    lesson_body: Mapped[str] = mapped_column(Text, default="")
    importance: Mapped[int] = mapped_column(Integer, default=5)  # 1-10
    similar_past_trade_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
