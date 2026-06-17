import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class ResearchBrief(Base):
    """Research Agent output for a market — sentiment aggregation + narrative probability."""

    __tablename__ = "research_briefs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    market_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_markets.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    bullish_pct: Mapped[float] = mapped_column(Float, default=0.0)
    bearish_pct: Mapped[float] = mapped_column(Float, default=0.0)
    neutral_pct: Mapped[float] = mapped_column(Float, default=0.0)
    source_agreement_pct: Mapped[float] = mapped_column(Float, default=0.0)
    narrative_probability: Mapped[float] = mapped_column(Float, default=0.0)
    market_implied_probability: Mapped[float] = mapped_column(Float, default=0.0)
    gap_pct: Mapped[float] = mapped_column(Float, default=0.0)
    brief_text: Mapped[str] = mapped_column(Text, default="")
    reasoning_log: Mapped[list] = mapped_column(JSON, default=list)
    # [{source, title, url, sentiment, weight, published_at}]
    sources: Mapped[list] = mapped_column(JSON, default=list)
