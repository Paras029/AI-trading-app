"""
Fetches upcoming high-impact economic events from Forex Factory's public calendar.
No API key required. Returns gracefully empty list on any error.
"""
from datetime import datetime, timezone
import httpx
import structlog

log = structlog.get_logger()

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Title keywords → context tags emitted
EVENT_TAG_MAP = {
    "FOMC": ["fomc_week", "fed_event"],
    "FEDERAL RESERVE": ["fomc_week", "fed_event"],
    "RATE DECISION": ["fed_event"],
    "CPI": ["cpi_event"],
    "CONSUMER PRICE": ["cpi_event"],
    "NON-FARM": ["nfp_event"],
    "NFP": ["nfp_event"],
    "GDP": ["gdp_event"],
    "PMI": ["pmi_event"],
    "POWELL": ["fed_event"],
}


async def _fetch_raw_events() -> list[dict]:
    """Fetch and store raw calendar events in Redis with 24h TTL."""
    from app.core import redis_client
    cached = await redis_client.get_json("cache:ff_calendar")
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(FF_CALENDAR_URL, headers={"User-Agent": "ApexTradingBot/1.0"})
            resp.raise_for_status()
            events = resp.json()
        await redis_client.set_json("cache:ff_calendar", events, ttl=86400)
        log.info("event_calendar_fetched_fresh", count=len(events))
        return events
    except Exception as e:
        log.warning("event_calendar_fetch_failed", error=str(e))
        return []


async def fetch_upcoming_events(hours_ahead: int = 48) -> list[dict]:
    """
    Returns list of high-impact events within hours_ahead hours.
    Each item: {"title": str, "country": str, "hours_until": float, "tags": list[str]}
    Uses a 24h Redis cache to avoid Forex Factory rate limits (HTTP 429).
    """
    raw_events = await _fetch_raw_events()
    now = datetime.now(timezone.utc)
    result = []

    for ev in raw_events:
        if ev.get("impact", "").lower() not in ("high", "3"):
            continue
        try:
            ev_time = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue

        hours_until = (ev_time - now).total_seconds() / 3600
        if not (0 < hours_until <= hours_ahead):
            continue

        title = ev.get("title", "").upper()
        tags: list[str] = []
        for keyword, event_tags in EVENT_TAG_MAP.items():
            if keyword in title:
                tags.extend(event_tags)

        result.append({
            "title": ev.get("title", "Unknown Event"),
            "country": ev.get("country", ""),
            "hours_until": round(hours_until, 1),
            "tags": list(set(tags)),
        })

    result.sort(key=lambda e: e["hours_until"])
    log.debug("upcoming_events_filtered", count=len(result))
    return result
