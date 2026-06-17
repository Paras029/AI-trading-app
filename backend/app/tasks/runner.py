"""
Starts/stops the always-on background asyncio tasks on app startup/shutdown — currently
just the WebSocket Redis listener. The 5-stage prediction pipeline (orchestrator.py) is
user-controlled via POST /api/settings/start|stop, not auto-started here.
"""
import asyncio
import structlog
from app.core.websocket_manager import manager

log = structlog.get_logger()

_tasks: list[asyncio.Task] = []


async def start_all() -> None:
    log.info("starting_background_tasks")
    _tasks.append(asyncio.create_task(manager.start_redis_listener(), name="ws_listener"))
    log.info("all_tasks_started", count=len(_tasks))


async def stop_all() -> None:
    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    log.info("all_tasks_stopped")
