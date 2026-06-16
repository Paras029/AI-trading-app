"""
Market hours awareness — knows when each market is open/closed.
"""
from zoneinfo import ZoneInfo
from datetime import datetime, time, date, timedelta

MARKET_HOURS = {
    "us_stocks": {
        "tz": "America/New_York",
        "open": time(9, 30),
        "close": time(16, 0),
        "days": range(0, 5),  # Mon–Fri
    },
    "india_stocks": {
        "tz": "Asia/Kolkata",
        "open": time(9, 15),
        "close": time(15, 30),
        "days": range(0, 5),
    },
    "forex": {
        "tz": "UTC",
        "open": time(0, 0),
        "close": time(23, 59),
        "days": range(0, 5),  # Mon–Fri (closed weekends)
    },
    "crypto": None,  # 24/7, always open
}


def is_market_open(market: str) -> bool:
    cfg = MARKET_HOURS.get(market)
    if cfg is None:
        return True  # crypto — always open
    now = datetime.now(ZoneInfo(cfg["tz"]))
    return now.weekday() in cfg["days"] and cfg["open"] <= now.time() <= cfg["close"]


def minutes_to_close(market: str) -> int | None:
    """Returns minutes until market closes, or None if closed or always open."""
    cfg = MARKET_HOURS.get(market)
    if cfg is None:
        return None
    now = datetime.now(ZoneInfo(cfg["tz"]))
    if not is_market_open(market):
        return None
    close_dt = datetime.combine(now.date(), cfg["close"], tzinfo=now.tzinfo)
    return max(0, int((close_dt - now).total_seconds() / 60))


def market_status_all() -> dict[str, bool]:
    return {m: is_market_open(m) for m in ["crypto", "us_stocks", "india_stocks", "forex"]}
