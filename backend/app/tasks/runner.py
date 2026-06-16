"""
Starts all background asyncio tasks on app startup.
"""
import asyncio
import structlog
from app.services.market_data.ccxt_ws import run_crypto_feed
from app.services.market_data.alpaca_feed import run_us_feed
from app.services.market_data.kite_feed import run_india_feed
from app.services.market_data.world_feed import run_world_feed_loop
from app.services.pipeline import run_sl_monitor, run_signal_loop
from app.core.websocket_manager import manager

log = structlog.get_logger()

_tasks: list[asyncio.Task] = []

_MARKETS = ["crypto", "us_stocks", "india_stocks", "forex"]


async def start_all() -> None:
    log.info("starting_background_tasks")
    _tasks.extend([
        # Market data feeds
        asyncio.create_task(run_crypto_feed(), name="crypto_feed"),
        asyncio.create_task(run_us_feed(), name="us_feed"),
        asyncio.create_task(run_india_feed(), name="india_feed"),
        asyncio.create_task(run_world_feed_loop(), name="world_feed"),
        # WebSocket broadcaster
        asyncio.create_task(manager.start_redis_listener(), name="ws_listener"),
    ])
    # Per-market: fast SL/TP loop (10s) + slow signal loop (60s)
    for market in _MARKETS:
        _tasks.append(asyncio.create_task(run_sl_monitor(market), name=f"sl_monitor_{market}"))
        _tasks.append(asyncio.create_task(run_signal_loop(market), name=f"signal_loop_{market}"))

    log.info("all_tasks_started", count=len(_tasks))


async def stop_all() -> None:
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    log.info("all_tasks_stopped")
