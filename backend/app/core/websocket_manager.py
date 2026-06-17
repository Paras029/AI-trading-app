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
        """
        Subscribe to all pipeline Redis pub/sub channels and forward to WebSocket clients.

        Channel -> WS `type` mapping (colon-separated Redis channels collapse to the
        underscore-separated `type` values the frontend's useWebSocket.ts switch
        statement expects):

            scanner:activity      -> scanner_activity
            research:activity     -> research_activity
            prediction:activity   -> prediction_activity
            risk:activity         -> risk_activity
            risk:decision         -> risk_decision
            postmortem:new        -> postmortem_new
            pipeline:status       -> pipeline_status
            trade_update:paper    -> trade_update
            trade_update:live     -> trade_update

        `prediction:signal` and `risk:queued` are internal pipeline-coordination
        channels only (orchestrator.py signaling itself across stages) — they have
        no corresponding frontend handler and are intentionally NOT subscribed here.
        """
        client = redis_client.get_client()
        pubsub = client.pubsub()
        await pubsub.psubscribe(
            "scanner:activity",
            "research:activity",
            "prediction:activity",
            "risk:activity",
            "risk:decision",
            "postmortem:new",
            "pipeline:status",
            "trade_update:*",
        )
        log.info("WebSocket Redis listener started")
        async for message in pubsub.listen():
            if message["type"] not in ("pmessage", "message"):
                continue
            try:
                channel = message.get("channel", "")
                payload = json.loads(message["data"])
                market = payload.get("market", "all")
                # Derive event type from channel name (prefix-based — trade_update:paper
                # and trade_update:live both collapse to the single type "trade_update").
                if channel.startswith("scanner:activity"):
                    event_type = "scanner_activity"
                elif channel.startswith("research:activity"):
                    event_type = "research_activity"
                elif channel.startswith("prediction:activity"):
                    event_type = "prediction_activity"
                elif channel.startswith("risk:decision"):
                    event_type = "risk_decision"
                elif channel.startswith("risk:activity"):
                    event_type = "risk_activity"
                elif channel.startswith("postmortem:new"):
                    event_type = "postmortem_new"
                elif channel.startswith("pipeline:status"):
                    event_type = "pipeline_status"
                elif channel.startswith("trade_update:"):
                    event_type = "trade_update"
                else:
                    event_type = "update"
                await self.broadcast(event_type, payload, market)
            except Exception as e:
                log.warning("ws_listener_error", error=str(e))


manager = ConnectionManager()
