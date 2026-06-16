"""
Indicator engine: reads OHLCV candles from Redis and computes
RSI, MACD, Bollinger Bands, EMA(20), EMA(50), ADX via pandas-ta.
"""
import pandas as pd
import pandas_ta as ta
import structlog
from app.core import redis_client

log = structlog.get_logger()


async def compute_indicators(symbol: str, interval: str = "1m") -> dict | None:
    candles = await redis_client.zrange_candles(symbol, interval, limit=200)
    if len(candles) < 50:
        return None

    df = pd.DataFrame(candles, columns=["t", "o", "h", "l", "c", "v", "symbol", "market"])
    df = df[["t", "o", "h", "l", "c", "v"]].astype({"o": float, "h": float, "l": float, "c": float, "v": float})
    df.sort_values("t", inplace=True)
    df.reset_index(drop=True, inplace=True)

    close = df["c"]
    high = df["h"]
    low = df["l"]

    rsi = ta.rsi(close, length=14)
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    bb = ta.bbands(close, length=20, std=2.0)
    ema20 = ta.ema(close, length=20)
    ema50 = ta.ema(close, length=50)
    adx_df = ta.adx(high, low, close, length=14)

    def safe(series, idx=-1):
        try:
            v = series.iloc[idx]
            return round(float(v), 6) if pd.notna(v) else None
        except Exception:
            return None

    snapshot = {
        "rsi": safe(rsi),
        "macd": {
            "macd": safe(macd_df["MACD_12_26_9"]) if macd_df is not None else None,
            "signal": safe(macd_df["MACDs_12_26_9"]) if macd_df is not None else None,
            "histogram": safe(macd_df["MACDh_12_26_9"]) if macd_df is not None else None,
        },
        "bollinger": {
            "upper": safe(bb["BBU_20_2.0"]) if bb is not None else None,
            "middle": safe(bb["BBM_20_2.0"]) if bb is not None else None,
            "lower": safe(bb["BBL_20_2.0"]) if bb is not None else None,
        },
        "ema_20": safe(ema20),
        "ema_50": safe(ema50),
        "adx": safe(adx_df["ADX_14"]) if adx_df is not None else None,
        "current_price": safe(close),
    }

    await redis_client.set_json(f"indicators:{symbol}", snapshot, ttl=120)
    return snapshot
