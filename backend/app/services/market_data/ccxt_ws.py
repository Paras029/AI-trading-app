"""
Binance WebSocket market data feed via ccxt.pro.
Publishes OHLCV candles and price ticks to Redis.
"""
import asyncio
import time
import structlog
from app.core import redis_client
from app.config import settings

log = structlog.get_logger()

SYMBOLS = ["BTC/USDT", "ETH/USDT"]
INTERVAL = "1m"


async def run_crypto_feed() -> None:
    try:
        import ccxt.pro as ccxtpro
    except ImportError:
        log.error("ccxt not installed — crypto feed disabled")
        return

    exchange = ccxtpro.binance({
        "apiKey": settings.binance_api_key or None,
        "secret": settings.binance_secret or None,
        "options": {"defaultType": "future"},
    })

    log.info("crypto_feed_starting", symbols=SYMBOLS)

    async def watch_symbol(symbol: str) -> None:
        while True:
            try:
                ohlcvs = await exchange.watch_ohlcv(symbol, INTERVAL)
                for ohlcv in ohlcvs:
                    ts, o, h, l, c, v = ohlcv
                    candle = {"t": ts, "o": o, "h": h, "l": l, "c": c, "v": v, "symbol": symbol, "market": "crypto"}
                    key = symbol.replace("/", "")
                    await redis_client.zadd_candle(key, INTERVAL, ts, candle)
                    await redis_client.publish(f"ticks:{key}", {
                        "symbol": symbol, "market": "crypto",
                        "price": c, "volume": v, "ts": ts,
                    })
            except Exception as e:
                log.warning("crypto_feed_error", symbol=symbol, error=str(e))
                await asyncio.sleep(5)

    tasks = [asyncio.create_task(watch_symbol(s)) for s in SYMBOLS]
    try:
        await asyncio.gather(*tasks)
    finally:
        await exchange.close()
