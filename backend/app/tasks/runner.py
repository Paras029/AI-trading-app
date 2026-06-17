"""
Starts/stops all background asyncio tasks on app startup/shutdown: the 5-stage prediction
pipeline (orchestrator.py) plus the WebSocket Redis listener.
"""
import asyncio
import structlog
from app.services import orchestrator
from app.core.websocket_manager import manager

log = structlog.get_logger()

_tasks: list[asyncio.Task] = []


async def start_all() -> None:
    log.info("starting_background_tasks")
    _tasks.append(asyncio.create_task(manager.start_redis_listener(), name="ws_listener"))
    await orchestrator.start_all()
    log.info("all_tasks_started", count=len(_tasks))


async def stop_all() -> None:
    await orchestrator.stop_all()
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    log.info("all_tasks_stopped")
