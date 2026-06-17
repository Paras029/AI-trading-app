import uuid
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Trade(Base):
    """A filled position on a prediction market. Created only after all 9 risk gates pass.
    An open Trade row IS the position — no separate Position model (no leverage/liquidation
    in prediction markets)."""

    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id: Mapped[str] = mapped_column(String, ForeignKey("portfolios.id"), index=True)
    market_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_markets.id"), index=True)
    signal_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_signals.id"), index=True)
    mode: Mapped[str] = mapped_column(String, default="paper")  # paper | live
    side: Mapped[str] = mapped_column(String)                   # YES | NO
    entry_price: Mapped[float] = mapped_column(Float)
    shares: Mapped[float] = mapped_column(Float)
    stake_usdc: Mapped[float] = mapped_column(Float)
    kelly_fraction_used: Mapped[float] = mapped_column(Float, default=0.0)
    full_kelly_fraction: Mapped[float] = mapped_column(Float, default=0.0)
    risk_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    exec_venue: Mapped[str] = mapped_column(String, default="paper")  # paper | polymarket_clob
    exec_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    exec_tx_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # open | settled_win | settled_loss | settled_void | cancelled
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
