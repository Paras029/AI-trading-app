import asyncio
import json
import structlog
from fastapi import WebSocket
from app.core import redis_client

log = structlog.get_logger()


class ConnectionManager:
    def __init__(self):
        # market -> set of websocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, market: str = "all") -> None:
        await ws.accept()
        async with self._lock:
            self._connections.setdefault(market, set()).add(ws)
            self._connections.setdefault("all", set()).add(ws)

    async def disconnect(self, ws: WebSocket, market: str = "all") -> None:
        async with self._lock:
            for s in self._connections.values():
                s.discard(ws)

    async def broadcast(self, event_type: str, data: dict, market: str = "all") -> None:
        message = json.dumps({"type": event_type, "data": data})
        targets = self._connections.get(market, set()) | self._connections.get("all", set())
        dead = set()
        for ws in list(targets):
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=2.0)
            except Exception:
                dead.add(ws)
        async with self._lock:
            for ws in dead:
                for s in self._connections.values():
                    s.discard(ws)

    async def start_redis_listener(self) -> None:
        """Subscribe to all Redis pub/sub channels and forward to WebSocket clients."""
        client = redis_client.get_client()
        pubsub = client.pubsub()
        await pubsub.psubscribe("ticks:*", "signal:*", "trade_update:*", "position_update:*", "world_update", "episode_update:*")
        log.info("WebSocket Redis listener started")
        async for message in pubsub.listen():
            if message["type"] not in ("pmessage", "message"):
                continue
            try:
                channel = message.get("channel", "")
                payload = json.loads(message["data"])
                market = payload.get("market", "all")
                # Derive event type from channel name
                if channel.startswith("ticks:"):
                    event_type = "price_tick"
                elif channel.startswith("signal:"):
                    event_type = "signal_new"
                elif channel.startswith("trade_update:"):
                    event_type = "trade_update"
                elif channel.startswith("position_update:"):
                    event_type = "position_update"
                elif channel == "world_update":
                    event_type = "world_update"
                elif channel.startswith("episode_update:"):
                    event_type = "episode_update"
                else:
                    event_type = "update"
                await self.broadcast(event_type, payload, market)
            except Exception as e:
                log.warning("ws_listener_error", error=str(e))


manager = ConnectionManager()
