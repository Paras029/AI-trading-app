import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class RiskGateCheck(Base):
    """One row per gate per evaluation — 9 rows per signal that reaches the Risk stage."""

    __tablename__ = "risk_gate_checks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_id: Mapped[str] = mapped_column(String, ForeignKey("prediction_signals.id"), index=True)
    # kill_switch | edge_threshold | position_size_pct | single_position_cap |
    # total_exposure_pct | position_count | max_drawdown | daily_loss_limit | slippage_check
    gate_name: Mapped[str] = mapped_column(String)
    sequence: Mapped[int] = mapped_column(Integer)  # 1-9
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold_value: Mapped[float] = mapped_column(Float, default=0.0)
    actual_value: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str] = mapped_column(String, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
