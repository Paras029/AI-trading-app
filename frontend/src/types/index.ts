export type Market = "crypto" | "us_stocks" | "india_stocks" | "forex";
export type EpisodeOutcome = "running" | "goal" | "blowup";
export type StrategyStatus = "active" | "candidate" | "retired";
export type TradeAction = "BUY" | "SELL" | "HOLD";

export interface Episode {
  id: string;
  market: Market;
  generation: number;
  start_equity: number;
  goal_equity: number;
  current_equity: number;
  peak_equity: number;
  num_trades: number;
  outcome: EpisodeOutcome;
  start_at: string;
  end_at: string | null;
}

export interface Generation {
  id: string;
  market: Market;
  number: number;
  after_episode_id: string;
  summary_text: string;
  kelly_fraction: number;
  max_leverage: number;
  lessons_count: number;
  promoted_strategies: string;
  retired_strategies: string;
  created_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  market: Market;
  status: StrategyStatus;
  description: string;
  exp_r: number;
  profit_factor: number;
  sharpe: number;
  win_rate: number;
  num_trades: number;
}

export interface Lesson {
  id: string;
  episode_id: string;
  market: Market;
  title: string;
  body: string;
  market_regime: string;
  importance: number;
  created_at: string;
}

export interface Trade {
  id: string;
  episode_id: string;
  market: Market;
  symbol: string;
  side: "long" | "short";
  leverage: number;
  entry_price: number;
  exit_price: number | null;
  qty: number;
  notional: number;
  pnl: number | null;
  pnl_pct: number | null;
  reason: string;
  is_open: boolean;
  strategy_name: string;
  opened_at: string;
  closed_at: string | null;
}

export interface Position {
  id: string;
  episode_id: string;
  market: Market;
  symbol: string;
  side: "long" | "short";
  leverage: number;
  entry_price: number;
  mark_price: number;
  qty: number;
  notional: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  liquidation_price: number;
  liq_distance_pct: number;
  strategy_name: string;
  opened_at: string;
}

export interface AISignal {
  id?: string;
  market: Market;
  symbol: string;
  action: TradeAction;
  confidence: number;
  reasoning: string;
  risk_note: string;
  price_at_signal?: number;
  created_at?: string;
}

export interface WorldContext {
  updated_at: string;
  crypto_fng: { value: number; label: string };
  stock_fng: { value: number; label: string };
  regime: string;
  funding_rate: number;
  macro: Record<string, number>;
  headlines: { crypto: string[]; us: string[]; india: string[] };
}

export interface WsMessage {
  type: string;
  data: Record<string, unknown>;
}
