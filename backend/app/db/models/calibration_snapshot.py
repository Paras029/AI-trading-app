import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class CalibrationSnapshot(Base):
    """Periodic rollup of model/strategy performance, scoped to a Portfolio mode."""

    __tablename__ = "calibration_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    mode: Mapped[str] = mapped_column(String, index=True)  # paper | live
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    window: Mapped[str] = mapped_column(String, default="rolling_50")  # rolling_50 | alltime
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    brier_score: Mapped[float] = mapped_column(Float, default=0.0)
    avg_pnl_per_trade: Mapped[float] = mapped_column(Float, default=0.0)
    num_trades: Mapped[int] = mapped_column(Integer, default=0)
    xgboost_active: Mapped[bool] = mapped_column(Boolean, default=False)
