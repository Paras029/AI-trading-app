from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AI
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # Database
    database_url: str = "postgresql+asyncpg://trading:trading_local@localhost:5432/trading"
    redis_url: str = "redis://localhost:6379/0"

    # Trading
    trading_mode: Literal["paper", "live"] = "paper"
    episode_start_equity: float = 100.0
    episode_goal_multiplier: float = 5.0   # goal = start * multiplier
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

    # News & Sentiment
    news_api_key: str = ""
    crypto_panic_api_key: str = ""
    alpha_vantage_key: str = ""


settings = Settings()
