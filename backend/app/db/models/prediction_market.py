import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class PredictionMarket(Base):
    """Local cache of a Polymarket market, refreshed by the Scanner agent.
    PredictionMarket.status moves left-to-right through the pipeline stages."""

    __tablename__ = "prediction_markets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    polymarket_condition_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    polymarket_slug: Mapped[str] = mapped_column(String, default="")
    question: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, default="", index=True)
    outcomes: Mapped[list] = mapped_column(JSON, default=list)
    yes_token_id: Mapped[str] = mapped_column(String, default="")
    no_token_id: Mapped[str] = mapped_column(String, default="")
    current_yes_price: Mapped[float] = mapped_column(Float, default=0.0)
    volume_24h: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity: Mapped[float] = mapped_column(Float, default=0.0)
    expiry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # active | scanned | researched | signaled | risk_checked | traded | settled | rejected | expired
    status: Mapped[str] = mapped_column(String, default="active", index=True)
    resolved_outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
