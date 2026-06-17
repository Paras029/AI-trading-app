import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class MarketScan(Base):
    """One row per scanner pass over a market — an append-only pass/reject log."""

    __tablename__ = "market_scans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    market_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_markets.id"), index=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    reject_reason: Mapped[str] = mapped_column(String, default="")
    price_at_scan: Mapped[float] = mapped_column(Float, default=0.0)
    volume_at_scan: Mapped[float] = mapped_column(Float, default=0.0)
    spread_at_scan: Mapped[float] = mapped_column(Float, default=0.0)
    days_to_expiry: Mapped[float] = mapped_column(Float, default=0.0)
    naive_edge_pct: Mapped[float] = mapped_column(Float, default=0.0)
    flags: Mapped[dict] = mapped_column(JSON, default=dict)
