import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Portfolio(Base):
    """Continuous equity ledger — one row per trading mode (paper|live), created lazily
    on first trade in that mode. Replaces the old Episode model's role as the equity tracker."""

    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    mode: Mapped[str] = mapped_column(String, index=True)  # paper | live
    starting_balance: Mapped[float] = mapped_column(Float, default=1000.0)
    current_balance: Mapped[float] = mapped_column(Float, default=1000.0)
    total_equity: Mapped[float] = mapped_column(Float, default=1000.0)
    peak_equity: Mapped[float] = mapped_column(Float, default=1000.0)
    realized_pnl_today: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl_alltime: Mapped[float] = mapped_column(Float, default=0.0)
    num_trades_total: Mapped[int] = mapped_column(Integer, default=0)
    num_trades_open: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
