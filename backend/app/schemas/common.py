from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal


# ── Portfolio ────────────────────────────────────────────────────────────────

class PortfolioOut(BaseModel):
    id: str
    mode: str
    starting_balance: float
    current_balance: float
    total_equity: float
    peak_equity: float
    realized_pnl_today: float
    realized_pnl_alltime: float
    num_trades_total: int
    num_trades_open: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Markets / Scanner ──────────────────────────────────────────────────────

class PredictionMarketOut(BaseModel):
    id: str
    polymarket_condition_id: str
    polymarket_slug: str
    question: str
    category: str
    outcomes: list
    yes_token_id: str
    no_token_id: str
    current_yes_price: float
    volume_24h: float
    liquidity: float
    expiry_at: Optional[datetime] = None
    status: str
    resolved_outcome: Optional[str] = None
    resolved_at: Optional[datetime] = None
    first_seen_at: datetime
    last_scanned_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MarketScanOut(BaseModel):
    id: str
    market_id: str
    scanned_at: datetime
    passed: bool
    reject_reason: str
    price_at_scan: float
    volume_at_scan: float
    spread_at_scan: float
    days_to_expiry: float
    naive_edge_pct: float
    flags: dict

    model_config = {"from_attributes": True}


# ── Research ─────────────────────────────────────────────────────────────

class ResearchBriefOut(BaseModel):
    id: str
    market_id: str
    created_at: datetime
    bullish_pct: float
    bearish_pct: float
    neutral_pct: float
    source_agreement_pct: float
    narrative_probability: float
    market_implied_probability: float
    gap_pct: float
    brief_text: str
    reasoning_log: list
    sources: list

    model_config = {"from_attributes": True}


# ── Prediction ensemble ──────────────────────────────────────────────────

class ModelForecastOut(BaseModel):
    id: str
    market_id: str
    signal_id: Optional[str] = None
    role: str
    provider: str
    model: str
    probability: Optional[float] = None
    reasoning: Optional[str] = None
    weight_configured: float
    weight_applied: float
    latency_ms: Optional[int] = None
    status: str
    error_detail: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PredictionSignalOut(BaseModel):
    id: str
    market_id: str
    research_brief_id: Optional[str] = None
    ensemble_probability: float
    final_probability: float
    market_price: float
    edge: float
    expected_value: float
    z_score: float
    used_xgboost: bool
    feature_snapshot: dict
    action: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CalibrationSnapshotOut(BaseModel):
    id: str
    mode: str
    snapshot_at: datetime
    window: str
    win_rate: float
    sharpe_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    brier_score: float
    avg_pnl_per_trade: float
    num_trades: int
    xgboost_active: bool

    model_config = {"from_attributes": True}


# ── Risk ─────────────────────────────────────────────────────────────────

class RiskGateCheckOut(BaseModel):
    id: str
    signal_id: str
    gate_name: str
    sequence: int
    passed: Optional[bool] = None
    threshold_value: Optional[float] = None
    actual_value: Optional[float] = None
    detail: Optional[str] = None
    checked_at: datetime

    model_config = {"from_attributes": True}


# ── Trades ───────────────────────────────────────────────────────────────

class TradeOut(BaseModel):
    id: str
    portfolio_id: str
    market_id: str
    signal_id: str
    mode: str
    side: str
    entry_price: float
    shares: float
    stake_usdc: float
    kelly_fraction_used: float
    full_kelly_fraction: float
    risk_approved: bool
    exec_venue: str
    exec_order_id: Optional[str] = None
    exec_tx_hash: Optional[str] = None
    status: str
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    opened_at: datetime
    settled_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Post-mortem ─────────────────────────────────────────────────────────

class PostMortemOut(BaseModel):
    id: str
    trade_id: str
    market_id: str
    outcome: str
    analysis_text: str
    failure_category: Optional[str] = None
    lesson_title: str
    lesson_body: str
    importance: int
    similar_past_trade_ids: list
    created_at: datetime

    model_config = {"from_attributes": True}


class FailureBreakdownEntry(BaseModel):
    failure_category: str
    count: int
    pct: float


# ── Dashboard ────────────────────────────────────────────────────────────

class PipelineStatusCounts(BaseModel):
    scanner: int
    research: int
    prediction: int
    risk: int
    settlement: int


class DashboardData(BaseModel):
    portfolio: Optional[PortfolioOut] = None
    win_rate: float
    sharpe_ratio: float
    brier_score: float
    active_positions: int
    position_limit: int
    pipeline_status: PipelineStatusCounts
    system_status: Literal["operational", "degraded", "paused"]
    pnl_today: float
