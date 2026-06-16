from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.websocket_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, market: str = Query(default="all")):
    await manager.connect(ws, market)
    try:
        while True:
            data = await ws.receive_text()
            # Client can send {"type": "ping"} — just keep alive
    except WebSocketDisconnect:
        await manager.disconnect(ws, market)
