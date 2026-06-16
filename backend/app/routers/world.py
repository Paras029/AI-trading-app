from fastapi import APIRouter
from app.core import redis_client
from app.services.market_data.world_feed import refresh_world_context

router = APIRouter(prefix="/api/world", tags=["world"])


@router.get("")
async def get_world_context():
    context = await redis_client.get_json("world:context")
    if not context:
        await refresh_world_context()
        context = await redis_client.get_json("world:context") or {}
    return context
