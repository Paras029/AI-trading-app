"""
Starts all background asyncio tasks on app startup.
"""
import asyncio
import structlog
from app.services.market_data.ccxt_ws import run_crypto_feed
from app.services.market_data.alpaca_feed import run_us_feed
from app.services.market_data.kite_feed import run_india_feed
from app.services.market_data.world_feed import run_world_feed_loop
from app.services.pipeline import run_market_pipeline
from app.core.websocket_manager import manager

log = structlog.get_logger()

_tasks: list[asyncio.Task] = []


async def start_all() -> None:
    log.info("starting_background_tasks")
    _tasks.extend([
        asyncio.create_task(run_crypto_feed(), name="crypto_feed"),
        asyncio.create_task(run_us_feed(), name="us_feed"),
        asyncio.create_task(run_india_feed(), name="india_feed"),
        asyncio.create_task(run_world_feed_loop(), name="world_feed"),
        asyncio.create_task(run_market_pipeline("crypto"), name="pipeline_crypto"),
        asyncio.create_task(run_market_pipeline("us_stocks"), name="pipeline_us"),
        asyncio.create_task(run_market_pipeline("india_stocks"), name="pipeline_india"),
        asyncio.create_task(manager.start_redis_listener(), name="ws_listener"),
    ])
    log.info("all_tasks_started", count=len(_tasks))


async def stop_all() -> None:
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    log.info("all_tasks_stopped")
