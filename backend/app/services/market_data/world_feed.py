"""
World context feed: Fear & Greed, headlines, macro, sentiment.
Runs on a schedule and writes to Redis for all markets.
"""
import asyncio
import structlog
import httpx
import feedparser
import yfinance as yf
from datetime import datetime
from app.core import redis_client
from app.config import settings

log = structlog.get_logger()

CRYPTO_FNG_URL = "https://api.alternative.me/fng/?limit=1"
CRYPTO_PANIC_URL = "https://cryptopanic.com/api/v1/posts/?auth_token={key}&filter=hot&public=true"
NEWS_API_URL = "https://newsapi.org/v2/top-headlines?category=business&language=en&pageSize=10&apiKey={key}"

INDIA_RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.moneycontrol.com/rss/latestnews.xml",
]

US_RSS_FEEDS = [
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.cnbc.com/id/20910258/device/rss/rss.html",
]

MACRO_TICKERS = {
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "GOLD": "GC=F",
    "OIL": "CL=F",
    "SP500": "^GSPC",
    "NIFTY50": "^NSEI",
    "SENSEX": "^BSESN",
    "BTCUSD": "BTC-USD",
}


async def fetch_crypto_fng() -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(CRYPTO_FNG_URL)
            d = r.json()["data"][0]
            return {"value": int(d["value"]), "label": d["value_classification"]}
    except Exception:
        return {"value": 50, "label": "Neutral"}


async def fetch_crypto_headlines() -> list[dict]:
    items = []
    if settings.crypto_panic_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                url = CRYPTO_PANIC_URL.format(key=settings.crypto_panic_api_key)
                r = await client.get(url)
                for post in r.json().get("results", [])[:8]:
                    items.append({"title": post["title"], "url": post.get("url", "")})
        except Exception:
            pass
    return items


async def fetch_rss_headlines(feeds: list[str], limit: int = 5) -> list[dict]:
    items = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                if title:
                    items.append({"title": title, "url": link})
        except Exception:
            pass
    return items[:10]


async def fetch_macro() -> dict:
    loop = asyncio.get_event_loop()
    def _fetch():
        result = {}
        for name, ticker in MACRO_TICKERS.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="2d")
                if not hist.empty:
                    result[name] = round(float(hist["Close"].iloc[-1]), 4)
            except Exception:
                pass
        return result
    return await loop.run_in_executor(None, _fetch)


async def fetch_funding_rate() -> float:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
            return float(r.json().get("lastFundingRate", 0))
    except Exception:
        return 0.0


def detect_regime(macro: dict, fng_value: int) -> str:
    vix = macro.get("VIX", 20)
    if fng_value < 25 or vix > 30:
        return "Risk Off"
    if fng_value > 65 and vix < 18:
        return "Risk On"
    return "Neutral"


async def refresh_world_context() -> None:
    log.info("world_feed_refreshing")
    from app.services.market_data.economic_calendar import fetch_upcoming_events

    fng, crypto_news, us_news, india_news, macro, funding, upcoming = await asyncio.gather(
        fetch_crypto_fng(),
        fetch_crypto_headlines(),
        fetch_rss_headlines(US_RSS_FEEDS),
        fetch_rss_headlines(INDIA_RSS_FEEDS),
        fetch_macro(),
        fetch_funding_rate(),
        fetch_upcoming_events(48),
        return_exceptions=True,
    )
    fng = fng if isinstance(fng, dict) else {"value": 50, "label": "Neutral"}
    macro = macro if isinstance(macro, dict) else {}
    upcoming = upcoming if isinstance(upcoming, list) else []

    regime = detect_regime(macro, fng.get("value", 50))

    context = {
        "updated_at": datetime.utcnow().isoformat(),
        "crypto_fng": fng,
        "stock_fng": {"value": 50, "label": "Neutral"},
        "regime": regime,
        "funding_rate": funding if isinstance(funding, float) else 0.0,
        "macro": macro,
        "upcoming_events": upcoming,
        "headlines": {
            "crypto": crypto_news if isinstance(crypto_news, list) else [],
            "us": us_news if isinstance(us_news, list) else [],
            "india": india_news if isinstance(india_news, list) else [],
        },
    }
    await redis_client.set_json("world:context", context, ttl=600)
    await redis_client.publish("world_update", {"market": "all", **context})
    log.info("world_feed_refreshed", regime=regime, upcoming_events=len(upcoming))


async def run_world_feed_loop(interval_seconds: int = 300) -> None:
    while True:
        await refresh_world_context()
        await asyncio.sleep(interval_seconds)
