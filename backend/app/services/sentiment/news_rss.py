"""
Google News RSS — free, no API key, reuses the feedparser pattern from the old
world_feed.py::fetch_rss_headlines.
"""
import asyncio
from urllib.parse import quote_plus
import feedparser
import structlog

log = structlog.get_logger()

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"


def _parse_feed(url: str, limit: int) -> list[dict]:
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            published = entry.get("published", "")
            source = ""
            if hasattr(entry, "source") and isinstance(entry.source, dict):
                source = entry.source.get("title", "")
            if title:
                items.append({
                    "source": "news_rss",
                    "publisher": source,
                    "title": title,
                    "url": link,
                    "published_at": published,
                })
    except Exception as e:
        log.warning("news_rss_parse_failed", url=url, error=str(e))
    return items


async def fetch_news_for_market(question: str, limit: int = 10) -> list[dict]:
    """Query Google News RSS for headlines relevant to a market question."""
    query = quote_plus(question[:200])
    url = f"{GOOGLE_NEWS_RSS_BASE}?q={query}&hl=en-US&gl=US&ceid=US:en"

    loop = asyncio.get_event_loop()
    try:
        items = await loop.run_in_executor(None, _parse_feed, url, limit)
        return items
    except Exception as e:
        log.error("fetch_news_for_market_failed", question=question[:80], error=str(e))
        return []
