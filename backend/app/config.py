from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AI
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"          # used for episode reviews / post-mortems (kept high quality)
    claude_model_fast: str = "claude-haiku-4-5-20251001"  # used for signals by default
    google_api_key: str = ""    # Google Gemini — free tier available
    openai_api_key: str = ""
    deepseek_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://trading:trading_local@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    # Trading
    trading_mode: Literal["paper", "live"] = "paper"
    prediction_trading_mode: Literal["paper", "live"] = "paper"
    bot_name: str = "Apex Prediction Bot"
    bot_version: str = "v2"

    # Polymarket (live execution only — never logged)
    polymarket_private_key: str = ""
    polymarket_funder_address: str = ""

    # Portfolio
    portfolio_starting_balance: float = 1000.0

    # XGBoost ensemble blending
    xgboost_min_samples: int = 30
    xgboost_retrain_interval: int = 10

    # News & Sentiment
    news_api_key: str = ""   # optional NewsAPI fallback


settings = Settings()

# ── Models available for selection in the UI ──────────────────────────────────
# Only models listed here will appear in the Settings page dropdown.
AVAILABLE_SIGNAL_MODELS = [
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash — Free (Recommended)",
        "provider": "google",
        "tier": "free",
        "input_cost_per_m": 0.0,
        "output_cost_per_m": 0.0,
        "description": "Current free-tier Gemini model. 15 RPM. Requires GOOGLE_API_KEY.",
    },
    {
        "id": "gemini-2.0-flash-lite",
        "name": "Gemini 2.0 Flash Lite — Free",
        "provider": "google",
        "tier": "free",
        "input_cost_per_m": 0.0,
        "output_cost_per_m": 0.0,
        "description": "Lighter, higher quota. Fallback if 2.0 Flash hits limits.",
    },
    {
        "id": "claude-haiku-4-5-20251001",
        "name": "Haiku 4.5 — Fast & cheap",
        "provider": "anthropic",
        "tier": "fast",
        "input_cost_per_m": 0.80,
        "output_cost_per_m": 4.00,
        "description": "~200ms latency. Best for high-frequency signals when indicators are clear.",
    },
    {
        "id": "claude-sonnet-4-6",
        "name": "Sonnet 4.6 — Balanced (Recommended)",
        "provider": "anthropic",
        "tier": "quality",
        "input_cost_per_m": 3.00,
        "output_cost_per_m": 15.00,
        "description": "Best reasoning for ambiguous setups. Recommended during early episodes.",
    },
]

# ── Forecast ensemble roles (source of truth the Settings UI renders from) ────
AVAILABLE_FORECAST_ROLES = [
    {
        "role": "primary_forecaster",
        "provider": "anthropic",
        "default_model": "claude-sonnet-4-6",
        "default_weight": 0.30,
        "requires_key": "anthropic_api_key",
    },
    {
        "role": "news_analyst",
        "provider": "anthropic",
        "default_model": "claude-haiku-4-5-20251001",
        "default_weight": 0.20,
        "requires_key": "anthropic_api_key",
    },
    {
        "role": "bull_advocate",
        "provider": "openai",
        "default_model": "gpt-4o",
        "default_weight": 0.20,
        "requires_key": "openai_api_key",
    },
    {
        "role": "bear_advocate",
        "provider": "google",
        "default_model": "gemini-2.0-flash",
        "default_weight": 0.15,
        "requires_key": "google_api_key",
    },
    {
        "role": "risk_contrarian",
        "provider": "deepseek",
        "default_model": "deepseek-chat",
        "default_weight": 0.15,
        "requires_key": "deepseek_api_key",
    },
]

# ── Prompt depth presets ───────────────────────────────────────────────────────
# NOTE: retained even though the old indicator-signal pipeline that consumed this is being
# rewritten in parallel — leave in place unless/until confirmed dead, since prompt-depth-style
# presets may still be useful for the new research/forecast prompt builders.
PROMPT_DEPTH_CONFIG = {
    "compact":  {"candles": 3,  "headlines": 2, "knowledge": 1, "historical": 0, "max_tokens": 350},
    "standard": {"candles": 5,  "headlines": 3, "knowledge": 2, "historical": 1, "max_tokens": 550},
    "rich":     {"candles": 10, "headlines": 5, "knowledge": 3, "historical": 2, "max_tokens": 800},
}

# ── Risk gate defaults ─────────────────────────────────────────────────────────
RISK_GATE_DEFAULTS = {
    "min_edge_pct": 0.05,
    "max_position_pct": 0.05,
    "single_position_cap_usd": 100.0,
    "max_total_exposure_pct": 0.40,
    "max_concurrent_positions": 8,
    "max_drawdown_pct": 0.25,
    "daily_loss_limit_pct": 0.10,
    "max_slippage_pct": 0.03,
    "kelly_multiplier": 0.25,
}

# ── Default runtime bot config (stored in Redis, editable via UI) ─────────────
DEFAULT_BOT_CONFIG = {
    **RISK_GATE_DEFAULTS,
    "prediction_trading_mode": "paper",
    "live_armed": False,   # never default True — must be explicitly armed via POST /api/settings/arm-live
    "forecast_role_weights": {r["role"]: r["default_weight"] for r in AVAILABLE_FORECAST_ROLES},
    "forecast_role_models": {r["role"]: r["default_model"] for r in AVAILABLE_FORECAST_ROLES},
    "scan_interval_seconds": 300,
    "scanner_categories": ["politics", "crypto", "sports", "pop-culture"],
    "scanner_min_volume": 5000,
    "scanner_max_expiry_days": 30,
    "scanner_min_edge_pct": 0.05,
}
