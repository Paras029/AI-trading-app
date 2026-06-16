from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class EpisodeOut(BaseModel):
    id: str
    market: str
    generation: int
    start_equity: float
    goal_equity: float
    current_equity: float
    peak_equity: float
    num_trades: int
    outcome: str
    start_at: datetime
    end_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GenerationOut(BaseModel):
    id: str
    market: str
    number: int
    after_episode_id: str
    summary_text: str
    kelly_fraction: float
    max_leverage: int
    lessons_count: int
    promoted_strategies: str
    retired_strategies: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StrategyOut(BaseModel):
    id: str
    name: str
    market: str
    status: str
    description: str
    exp_r: float
    profit_factor: float
    sharpe: float
    win_rate: float
    num_trades: int

    model_config = {"from_attributes": True}


class LessonOut(BaseModel):
    id: str
    episode_id: str
    market: str
    title: str
    body: str
    market_regime: str
    importance: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TradeOut(BaseModel):
    id: str
    episode_id: str
    market: str
    symbol: str
    side: str
    leverage: int
    entry_price: float
    exit_price: Optional[float] = None
    qty: float
    notional: float
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    reason: str
    is_open: bool
    strategy_name: str
    opened_at: datetime
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PositionOut(BaseModel):
    id: str
    episode_id: str
    market: str
    symbol: str
    side: str
    leverage: int
    entry_price: float
    mark_price: float
    qty: float
    notional: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    liquidation_price: float
    liq_distance_pct: float
    strategy_name: str
    opened_at: datetime

    model_config = {"from_attributes": True}


class SignalOut(BaseModel):
    id: str
    market: str
    symbol: str
    action: str
    confidence: float
    reasoning: str
    risk_note: str
    price_at_signal: float
    created_at: datetime

    model_config = {"from_attributes": True}
