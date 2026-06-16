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


async def fetch_upcoming_events(hours_ahead: int = 48) -> list[dict]:
    """
    Returns list of high-impact events within hours_ahead hours.
    Each item: {"title": str, "country": str, "hours_until": float, "tags": list[str]}
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(FF_CALENDAR_URL, headers={"User-Agent": "ApexTradingBot/1.0"})
            resp.raise_for_status()
            events = resp.json()
    except Exception as e:
        log.warning("event_calendar_fetch_failed", error=str(e))
        return []

    now = datetime.now(timezone.utc)
    result = []

    for ev in events:
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
    log.debug("upcoming_events_fetched", count=len(result))
    return result
