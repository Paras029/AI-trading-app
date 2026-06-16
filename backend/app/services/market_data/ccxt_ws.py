"""
Crypto market data feed using yfinance REST polling.
No API key required — uses Yahoo Finance public data.
Polls every 60s and writes OHLCV candles to Redis.
"""
import asyncio
import structlog
from datetime import datetime
from app.core import redis_client

log = structlog.get_logger()

SYMBOL_MAP = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
}
INTERVAL = "1m"
POLL_SECONDS = 60


def _fetch_candles(yf_symbol: str) -> list[dict]:
    import yfinance as yf
    df = yf.download(yf_symbol, period="1d", interval="1m", progress=False, auto_adjust=True)
    if df.empty:
        return []
    rows = []
    for ts, row in df.tail(10).iterrows():
        rows.append({
            "t": int(ts.timestamp() * 1000),
            "o": float(row["Open"].iloc[0]) if hasattr(row["Open"], "iloc") else float(row["Open"]),
            "h": float(row["High"].iloc[0]) if hasattr(row["High"], "iloc") else float(row["High"]),
            "l": float(row["Low"].iloc[0]) if hasattr(row["Low"], "iloc") else float(row["Low"]),
            "c": float(row["Close"].iloc[0]) if hasattr(row["Close"], "iloc") else float(row["Close"]),
            "v": float(row["Volume"].iloc[0]) if hasattr(row["Volume"], "iloc") else float(row["Volume"]),
        })
    return rows


async def run_crypto_feed() -> None:
    log.info("crypto_feed_starting", symbols=list(SYMBOL_MAP.keys()), source="yfinance")
    loop = asyncio.get_event_loop()

    while True:
        for redis_symbol, yf_symbol in SYMBOL_MAP.items():
            try:
                candles = await loop.run_in_executor(None, _fetch_candles, yf_symbol)
                if not candles:
                    log.warning("crypto_feed_empty", symbol=redis_symbol)
                    continue

                for c in candles:
                    candle = {**c, "symbol": redis_symbol, "market": "crypto"}
                    await redis_client.zadd_candle(redis_symbol, INTERVAL, c["t"], candle)

                latest = candles[-1]
                await redis_client.publish(f"ticks:{redis_symbol}", {
                    "symbol": redis_symbol,
                    "market": "crypto",
                    "price": latest["c"],
                    "volume": latest["v"],
                    "ts": latest["t"],
                })
                log.debug("crypto_feed_updated", symbol=redis_symbol, price=latest["c"], candles=len(candles))

            except Exception as e:
                log.warning("crypto_feed_error", symbol=redis_symbol, error=str(e))

        await asyncio.sleep(POLL_SECONDS)
