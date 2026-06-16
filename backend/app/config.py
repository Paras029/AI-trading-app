from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AI
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"          # used for episode reviews (kept high quality)
    claude_model_fast: str = "claude-haiku-4-5-20251001"  # used for signals by default

    # Database
    database_url: str = "postgresql+asyncpg://trading:trading_local@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    # Trading
    trading_mode: Literal["paper", "live"] = "paper"
    episode_start_equity: float = 100.0
    episode_goal_multiplier: float = 5.0
    signal_cooldown_seconds: int = 60
    bot_name: str = "Apex Trading Bot"
    bot_version: str = "v1"

    # Alpaca (US Stocks)
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True

    # Binance (Crypto)
    binance_api_key: str = ""
    binance_secret: str = ""

    # Zerodha Kite (India Stocks)
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_user_id: str = ""
    kite_password: str = ""
    kite_totp_secret: str = ""

    # OANDA (Forex)
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_practice: bool = True

    # Google AI (Gemini — free tier available)
    google_api_key: str = ""

    # News & Sentiment
    news_api_key: str = ""
    crypto_panic_api_key: str = ""
    alpha_vantage_key: str = ""


settings = Settings()

# ── Models available for selection in the UI ──────────────────────────────────
# Only models listed here will appear in the Settings page dropdown.
AVAILABLE_SIGNAL_MODELS = [
    {
        "id": "gemini-2.0-flash",
        "name": "Gemini 2.0 Flash — Free",
        "provider": "google",
        "tier": "free",
        "input_cost_per_m": 0.0,
        "output_cost_per_m": 0.0,
        "description": "Google's fastest model. Free up to 1500 req/day. Requires GOOGLE_API_KEY.",
    },
    {
        "id": "gemini-1.5-flash",
        "name": "Gemini 1.5 Flash — Free",
        "provider": "google",
        "tier": "free",
        "input_cost_per_m": 0.0,
        "output_cost_per_m": 0.0,
        "description": "Reliable and fast. Free up to 1500 req/day. Requires GOOGLE_API_KEY.",
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

# ── Prompt depth presets ───────────────────────────────────────────────────────
PROMPT_DEPTH_CONFIG = {
    "compact":  {"candles": 3,  "headlines": 2, "knowledge": 1, "max_tokens": 300},
    "standard": {"candles": 5,  "headlines": 3, "knowledge": 2, "max_tokens": 400},
    "rich":     {"candles": 10, "headlines": 5, "knowledge": 5, "max_tokens": 600},
}

# ── Default runtime bot config (stored in Redis, editable via UI) ─────────────
DEFAULT_BOT_CONFIG = {
    "signal_model": settings.claude_model,   # users start on Sonnet
    "prompt_depth": "standard",
}
