// ── Execution / portfolio ────────────────────────────────────────────────
export type Mode = "paper" | "live";
export type TradeSide = "YES" | "NO";
export type TradeStatus = "open" | "settled_win" | "settled_loss" | "settled_void" | "cancelled";
export type SignalAction = "BUY_YES" | "BUY_NO" | "WATCH" | "SKIP";
export type ForecastStatus = "ok" | "skipped_no_key" | "error" | "timeout" | "thinking";
export type MarketStatus =
  | "active"
  | "scanned"
  | "researched"
  | "signaled"
  | "risk_checked"
  | "traded"
  | "settled"
  | "rejected"
  | "expired";
export type FailureCategory =
  | "bad_prediction"
  | "bad_timing"
  | "external_shock"
  | "bad_execution"
  | "overweighted_sentiment"
  | "model_overconfidence";
export type SystemStatus = "operational" | "degraded" | "paused";
export type GateName =
  | "kill_switch"
  | "edge_threshold"
  | "position_size_pct"
  | "single_position_cap"
  | "total_exposure_pct"
  | "position_count"
  | "max_drawdown"
  | "daily_loss_limit"
  | "slippage_check";

export interface Portfolio {
  id: string;
  mode: Mode;
  starting_balance: number;
  current_balance: number;
  total_equity: number;
  peak_equity: number;
  realized_pnl_today: number;
  realized_pnl_alltime: number;
  num_trades_total: number;
  num_trades_open: number;
  created_at: string;
  updated_at: string;
}

// ── Markets ───────────────────────────────────────────────────────────────
export interface PredictionMarket {
  id: string;
  polymarket_condition_id: string;
  polymarket_slug: string;
  question: string;
  category: string;
  outcomes: string[];
  yes_token_id: string;
  no_token_id: string;
  current_yes_price: number;
  volume_24h: number;
  liquidity: number;
  expiry_at: string;
  status: MarketStatus;
  resolved_outcome: string | null;
  resolved_at: string | null;
  first_seen_at: string;
  last_scanned_at: string;
}

export interface MarketScan {
  id: string;
  market_id: string;
  market?: PredictionMarket;
  scanned_at: string;
  passed: boolean;
  reject_reason: string | null;
  price_at_scan: number;
  volume_at_scan: number;
  spread_at_scan: number;
  days_to_expiry: number;
  naive_edge_pct: number;
  flags: Record<string, unknown>;
}

export interface ScannerFilters {
  categories: string[];
  min_volume: number;
  max_expiry_days: number;
  min_edge_pct: number;
}

// ── Research ─────────────────────────────────────────────────────────────
export interface ResearchSource {
  source: string;
  title: string;
  url: string;
  sentiment: "bullish" | "bearish" | "neutral";
  weight: number;
  published_at: string;
}

export interface ResearchBrief {
  id: string;
  market_id: string;
  market?: PredictionMarket;
  created_at: string;
  bullish_pct: number;
  bearish_pct: number;
  neutral_pct: number;
  source_agreement_pct: number;
  narrative_probability: number;
  market_implied_probability: number;
  gap_pct: number;
  brief_text: string;
  reasoning_log: string[];
  sources: ResearchSource[];
}

// ── Prediction ensemble ──────────────────────────────────────────────────
export interface ModelForecast {
  id: string;
  market_id: string;
  signal_id: string | null;
  role: string;
  provider: string;
  model: string;
  probability: number | null;
  reasoning: string | null;
  weight_configured: number;
  weight_applied: number;
  latency_ms: number | null;
  status: ForecastStatus;
  error_detail: string | null;
  created_at: string;
}

export interface PredictionSignal {
  id: string;
  market_id: string;
  market?: PredictionMarket;
  research_brief_id: string;
  ensemble_probability: number;
  final_probability: number;
  market_price: number;
  edge: number;
  expected_value: number;
  z_score: number;
  used_xgboost: boolean;
  feature_snapshot: Record<string, unknown>;
  action: SignalAction;
  created_at: string;
}

export interface CalibrationSnapshot {
  id: string;
  mode: Mode;
  snapshot_at: string;
  window: "rolling_50" | "alltime";
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  profit_factor: number;
  brier_score: number;
  avg_pnl_per_trade: number;
  num_trades: number;
  xgboost_active: boolean;
}

export interface CalibrationData {
  snapshot: CalibrationSnapshot | null;
  xgboost_active: boolean;
  xgboost_min_samples: number;
  settled_trade_count: number;
}

// ── Risk ─────────────────────────────────────────────────────────────────
export interface RiskGateCheck {
  id: string;
  signal_id: string;
  gate_name: GateName;
  sequence: number;
  passed: boolean | null;
  threshold_value: number | null;
  actual_value: number | null;
  detail: string | null;
  checked_at: string;
}

export interface RiskDecision {
  id: string;
  signal_id: string;
  market?: PredictionMarket;
  approved: boolean;
  trade_id: string | null;
  kelly_fraction_full: number;
  kelly_fraction_applied: number;
  stake_usdc: number;
  checked_at: string;
}

// ── Trades ───────────────────────────────────────────────────────────────
export interface Trade {
  id: string;
  portfolio_id: string;
  market_id: string;
  market?: PredictionMarket;
  signal_id: string;
  mode: Mode;
  side: TradeSide;
  entry_price: number;
  shares: number;
  stake_usdc: number;
  kelly_fraction_used: number;
  full_kelly_fraction: number;
  risk_approved: boolean;
  exec_venue: "paper" | "polymarket_clob";
  exec_order_id: string | null;
  exec_tx_hash: string | null;
  status: TradeStatus;
  exit_price: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  opened_at: string;
  settled_at: string | null;
}

export interface TradeDetail extends Trade {
  signal?: PredictionSignal;
  forecasts?: ModelForecast[];
  gate_checks?: RiskGateCheck[];
}

// ── Post-mortem ─────────────────────────────────────────────────────────
export interface PostMortem {
  id: string;
  trade_id: string;
  market_id: string;
  market?: PredictionMarket;
  outcome: "WIN" | "LOSS";
  analysis_text: string;
  failure_category: FailureCategory | null;
  lesson_title: string;
  lesson_body: string;
  importance: number;
  similar_past_trade_ids: string[];
  created_at: string;
}

export interface FailureBreakdownEntry {
  failure_category: FailureCategory;
  count: number;
  pct: number;
}

// ── Dashboard ────────────────────────────────────────────────────────────
export interface PipelineStatusCounts {
  scanner: number;
  research: number;
  prediction: number;
  risk: number;
  settlement: number;
}

export interface DashboardData {
  portfolio: Portfolio | null;
  win_rate: number;
  sharpe_ratio: number;
  brier_score: number;
  active_positions: number;
  position_limit: number;
  pipeline_status: PipelineStatusCounts;
  system_status: SystemStatus;
  pnl_today: number;
}

// ── Settings / config ───────────────────────────────────────────────────
export interface ForecastRoleConfig {
  role: string;
  provider: string;
  default_model: string;
  default_weight: number;
  requires_key: string;
  has_key?: boolean;
}

export interface RiskGateThresholds {
  min_edge_pct: number;
  max_position_pct: number;
  single_position_cap_usd: number;
  max_total_exposure_pct: number;
  max_concurrent_positions: number;
  max_drawdown_pct: number;
  daily_loss_limit_pct: number;
  max_slippage_pct: number;
  kelly_multiplier: number;
}

export interface BotConfig extends RiskGateThresholds {
  prediction_trading_mode: Mode;
  live_armed: boolean;
  forecast_role_weights: Record<string, number>;
  forecast_role_models: Record<string, string>;
  scan_interval_seconds: number;
  scanner_categories: string[];
  scanner_min_volume: number;
  scanner_max_expiry_days: number;
  scanner_min_edge_pct: number;
}

export interface ForecastModelOption {
  id: string;
  provider: string;
  label: string;
  tier: "free" | "cheap" | "premium";
  requires_key: string;
  has_key?: boolean;
}

export interface SettingsData {
  config: BotConfig;
  forecast_roles: ForecastRoleConfig[];
  forecast_models: ForecastModelOption[];
}

export interface BotStatus {
  paused: boolean;
}

// ── WebSocket envelope ──────────────────────────────────────────────────
export interface WsMessage {
  type: string;
  data: Record<string, unknown>;
}

// ── WS payload shapes (for store slices) ───────────────────────────────
export interface ScannerActivityEvent {
  ts: string;
  market_id?: string;
  question?: string;
  message: string;
  passed?: boolean;
}

export interface ResearchActivityEvent {
  ts: string;
  market_id: string;
  step: string;
  message: string;
}

export interface PredictionActivityEvent {
  market_id: string;
  role: string;
  provider: string;
  model: string;
  status: ForecastStatus;
  probability?: number | null;
  reasoning?: string | null;
}

export interface RiskActivityEvent {
  ts: string;
  signal_id: string;
  gate_name: GateName;
  sequence: number;
  passed: boolean | null;
  threshold_value?: number | null;
  actual_value?: number | null;
  detail?: string | null;
}

export interface PipelineStatusEvent extends PipelineStatusCounts {
  system_status: SystemStatus;
}
