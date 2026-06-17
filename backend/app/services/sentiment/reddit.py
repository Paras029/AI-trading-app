"""
Reddit public JSON search — no auth required, avoids praw's OAuth complexity.
Substitutes for Twitter/X sentiment (paid API tier not budgeted for this build —
disclosed in the UI via an InfoTooltip on the Research page).
"""
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger()

REDDIT_SEARCH_URL = "https://www.reddit.com/r/{sub}/search.json"

# Reddit blocks the default httpx/requests UA — a real-looking UA is required.
_USER_AGENT = "Mozilla/5.0 (compatible; ApexResearchBot/1.0; +https://github.com/apex-trading-bot)"

DEFAULT_SUBREDDITS = ["news", "worldnews", "politics", "PredictionMarkets", "wallstreetbets"]


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _search_subreddit(client: httpx.AsyncClient, sub: str, query: str, limit: int) -> list[dict]:
    url = REDDIT_SEARCH_URL.format(sub=sub)
    resp = await client.get(
        url,
        params={"q": query, "sort": "new", "limit": limit, "restrict_sr": "on"},
        headers={"User-Agent": _USER_AGENT},
    )
    if resp.status_code == 429:
        log.warning("reddit_rate_limited", sub=sub)
        return []
    resp.raise_for_status()
    data = resp.json()
    children = data.get("data", {}).get("children", [])
    posts = []
    for child in children:
        d = child.get("data", {})
        posts.append({
            "source": "reddit",
            "subreddit": sub,
            "title": d.get("title", ""),
            "url": f"https://reddit.com{d.get('permalink', '')}",
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "created_utc": d.get("created_utc"),
            "author": d.get("author", ""),
        })
    return posts


async def fetch_subreddit_posts(query: str, subreddits: list[str] | None = None, limit: int = 15) -> list[dict]:
    """Public JSON search across a list of subreddits, no auth required."""
    subs = subreddits or DEFAULT_SUBREDDITS
    results: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for sub in subs:
                try:
                    posts = await _search_subreddit(client, sub, query, limit)
                    results.extend(posts)
                except Exception as e:
                    log.warning("reddit_subreddit_search_failed", sub=sub, error=str(e))
    except Exception as e:
        log.error("reddit_fetch_failed", query=query, error=str(e))

    results.sort(key=lambda p: p.get("created_utc") or 0, reverse=True)
    return results[:limit]
