"""
Alpaca WebSocket feed for US stocks.
Uses alpaca-py SDK to stream bars → Redis.
"""
import asyncio
import structlog
from app.core import redis_client
from app.config import settings

log = structlog.get_logger()

US_SYMBOLS = ["AAPL", "NVDA", "TSLA", "SPY", "QQQ"]


async def run_us_feed() -> None:
    if not settings.alpaca_api_key:
        log.warning("alpaca_key_missing — US stock feed disabled")
        return
    try:
        from alpaca.data.live import StockDataStream
    except ImportError:
        log.error("alpaca-py not installed — US stock feed disabled")
        return

    stream = StockDataStream(settings.alpaca_api_key, settings.alpaca_secret_key)

    async def on_bar(bar) -> None:
        candle = {
            "t": int(bar.timestamp.timestamp() * 1000),
            "o": float(bar.open), "h": float(bar.high),
            "l": float(bar.low), "c": float(bar.close),
            "v": float(bar.volume),
            "symbol": bar.symbol, "market": "us_stocks",
        }
        await redis_client.zadd_candle(bar.symbol, "1m", candle["t"], candle)
        await redis_client.publish(f"ticks:{bar.symbol}", {
            "symbol": bar.symbol, "market": "us_stocks",
            "price": candle["c"], "volume": candle["v"], "ts": candle["t"],
        })

    stream.subscribe_bars(on_bar, *US_SYMBOLS)
    log.info("us_stock_feed_starting", symbols=US_SYMBOLS)
    await stream.run()
