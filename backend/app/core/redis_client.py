import json
import redis.asyncio as aioredis
from app.config import settings

_pool: aioredis.ConnectionPool | None = None


def get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return _pool


def get_client() -> aioredis.Redis:
    return aioredis.Redis(connection_pool=get_pool())


async def publish(channel: str, data: dict) -> None:
    async with get_client() as r:
        await r.publish(channel, json.dumps(data))


async def set_json(key: str, data: dict, ttl: int | None = None) -> None:
    async with get_client() as r:
        if ttl:
            await r.setex(key, ttl, json.dumps(data))
        else:
            await r.set(key, json.dumps(data))


async def get_json(key: str) -> dict | None:
    async with get_client() as r:
        raw = await r.get(key)
        return json.loads(raw) if raw else None


async def zadd_candle(symbol: str, interval: str, timestamp: int, candle: dict) -> None:
    async with get_client() as r:
        key = f"candles:{symbol}:{interval}"
        await r.zadd(key, {json.dumps(candle): timestamp})
        await r.zremrangebyrank(key, 0, -501)   # keep last 500


async def zrange_candles(symbol: str, interval: str, limit: int = 200) -> list[dict]:
    async with get_client() as r:
        key = f"candles:{symbol}:{interval}"
        raw = await r.zrange(key, -limit, -1)
        return [json.loads(c) for c in raw]


async def set_lock(key: str, ttl: int) -> bool:
    async with get_client() as r:
        return bool(await r.set(key, "1", ex=ttl, nx=True))


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.disconnect()
        _pool = None


# ── Bot runtime config ─────────────────────────────────────────────────────────

async def get_bot_config() -> dict:
    from app.config import DEFAULT_BOT_CONFIG
    data = await get_json("bot:config")
    if not data:
        return dict(DEFAULT_BOT_CONFIG)
    # Merge with defaults so new keys always have a value
    merged = dict(DEFAULT_BOT_CONFIG)
    merged.update(data)
    return merged


async def set_bot_config(updates: dict) -> dict:
    current = await get_bot_config()
    current.update(updates)
    await set_json("bot:config", current)
    return current
