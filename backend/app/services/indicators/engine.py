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
    if len(candles) < 20:
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

    # Also store previous histogram for crossover detection
    prev_histogram = safe(macd_df["MACDh_12_26_9"], -2) if macd_df is not None else None
    snapshot["_prev_macd_histogram"] = prev_histogram

    await redis_client.set_json(f"indicators:{symbol}", snapshot, ttl=120)
    return snapshot


def should_call_llm(indicators: dict) -> bool:
    """
    Pre-filter: returns True only when there is a potentially actionable setup.
    Eliminates ~70-80% of Claude calls when the market is flat/neutral.
    """
    if not indicators:
        return False

    rsi = indicators.get("rsi")
    bb = indicators.get("bollinger", {})
    macd = indicators.get("macd", {})
    price = indicators.get("current_price")
    adx = indicators.get("adx")
    ema20 = indicators.get("ema_20")
    ema50 = indicators.get("ema_50")
    histogram = macd.get("histogram")
    prev_histogram = indicators.get("_prev_macd_histogram")

    # Rule 1: RSI at notable levels (relaxed from 30/70 — paper mode, Gemini is free)
    if rsi is not None and (rsi < 35 or rsi > 65):
        return True

    # Rule 2: MACD histogram crossed zero
    if (histogram is not None and prev_histogram is not None
            and histogram != 0 and prev_histogram != 0
            and (histogram > 0) != (prev_histogram > 0)):
        return True

    # Rule 3: Price at or beyond Bollinger band
    if price and bb:
        lower = bb.get("lower")
        upper = bb.get("upper")
        if lower and price <= lower * 1.001:
            return True
        if upper and price >= upper * 0.999:
            return True

    # Rule 4: Trending market with EMA crossover
    if (adx is not None and adx > 25
            and ema20 is not None and ema50 is not None):
        prev_ema_diff_sign = None   # Would need previous values — skip for now
        # Simplified: strong trend with price well above/below both EMAs
        if price and price > max(ema20, ema50) * 1.005:
            return True
        if price and price < min(ema20, ema50) * 0.995:
            return True

    return False
