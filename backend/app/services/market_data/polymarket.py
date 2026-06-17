"""
Polymarket data client — Gamma API (market metadata) + CLOB API (orderbook/price).
No API key needed for reads; authenticated order placement lives in execution/polymarket_live.py.

Reuses the httpx.AsyncClient + tenacity.retry pattern from the old
signal_generator.py::_do_gemini_http.
"""
import uuid
from datetime import datetime, timezone
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import PredictionMarket

log = structlog.get_logger()

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"

_HTTP_TIMEOUT = 20


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=20))
async def _get(url: str, params: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        if not resp.is_success:
            log.warning("polymarket_http_error", url=url, status=resp.status_code, body=resp.text[:300])
        resp.raise_for_status()
        return resp


def _parse_outcomes(raw: dict) -> list[str]:
    outcomes = raw.get("outcomes")
    if isinstance(outcomes, str):
        import json as _json
        try:
            outcomes = _json.loads(outcomes)
        except Exception:
            outcomes = [outcomes]
    if not isinstance(outcomes, list):
        outcomes = ["Yes", "No"]
    return outcomes


def _parse_token_ids(raw: dict) -> tuple[str, str]:
    """Best-effort extraction of (yes_token_id, no_token_id) from a Gamma market payload."""
    token_ids = raw.get("clobTokenIds")
    if isinstance(token_ids, str):
        import json as _json
        try:
            token_ids = _json.loads(token_ids)
        except Exception:
            token_ids = []
    if not isinstance(token_ids, list):
        token_ids = []
    yes_id = token_ids[0] if len(token_ids) > 0 else ""
    no_id = token_ids[1] if len(token_ids) > 1 else ""
    return str(yes_id), str(no_id)


def _parse_yes_price(raw: dict) -> float:
    prices = raw.get("outcomePrices")
    if isinstance(prices, str):
        import json as _json
        try:
            prices = _json.loads(prices)
        except Exception:
            prices = []
    if isinstance(prices, list) and prices:
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return 0.0
    last_price = raw.get("lastTradePrice")
    try:
        return float(last_price) if last_price is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


async def fetch_markets(category: str | None = None, limit: int = 200, active_only: bool = True) -> list[dict]:
    """Fetch markets from the Gamma API. Returns raw market dicts."""
    params: dict = {"limit": limit, "order": "volume24hr", "ascending": "false"}
    if active_only:
        params["active"] = "true"
        params["closed"] = "false"
    if category:
        params["tag"] = category

    try:
        resp = await _get(f"{GAMMA_API_BASE}/markets", params=params)
        data = resp.json()
        if isinstance(data, dict):
            data = data.get("markets", data.get("data", []))
        return data if isinstance(data, list) else []
    except Exception as e:
        log.error("fetch_markets_failed", category=category, error=str(e))
        return []


async def fetch_orderbook(token_id: str) -> dict:
    """Fetch the CLOB orderbook for a token id. Returns {bids: [...], asks: [...]}."""
    if not token_id:
        return {"bids": [], "asks": []}
    try:
        resp = await _get(f"{CLOB_API_BASE}/book", params={"token_id": token_id})
        data = resp.json()
        return {
            "bids": data.get("bids", []) or [],
            "asks": data.get("asks", []) or [],
        }
    except Exception as e:
        log.warning("fetch_orderbook_failed", token_id=token_id, error=str(e))
        return {"bids": [], "asks": []}


async def fetch_price(token_id: str) -> float:
    """Fetch the current midpoint/last price for a token id."""
    if not token_id:
        return 0.0
    try:
        resp = await _get(f"{CLOB_API_BASE}/price", params={"token_id": token_id, "side": "buy"})
        data = resp.json()
        price = data.get("price")
        if price is not None:
            return float(price)
    except Exception as e:
        log.warning("fetch_price_failed", token_id=token_id, error=str(e))

    # Fall back to orderbook midpoint
    book = await fetch_orderbook(token_id)
    bids, asks = book.get("bids", []), book.get("asks", [])
    try:
        best_bid = float(bids[0]["price"]) if bids else None
        best_ask = float(asks[0]["price"]) if asks else None
        if best_bid is not None and best_ask is not None:
            return (best_bid + best_ask) / 2
        return best_bid or best_ask or 0.5
    except Exception:
        return 0.5


async def fetch_market_history(condition_id: str, interval: str = "1h") -> list[dict]:
    """Fetch price history for a market. Returns list of {t, p} points (timestamp, price)."""
    try:
        resp = await _get(
            f"{CLOB_API_BASE}/prices-history",
            params={"market": condition_id, "interval": interval, "fidelity": 10},
        )
        data = resp.json()
        history = data.get("history", [])
        return [{"t": p.get("t"), "p": p.get("p")} for p in history if isinstance(p, dict)]
    except Exception as e:
        log.debug("fetch_market_history_failed", condition_id=condition_id, error=str(e))
        return []


async def fetch_market_resolution(condition_id: str) -> str | None:
    """
    Check whether a market has resolved, returning 'YES'/'NO' if so, else None.
    Queried from the Gamma API (closed markets carry resolution info in outcomePrices —
    a resolved market settles its winning outcome's price to 1.0 and the loser's to 0.0).
    """
    if not condition_id:
        return None
    try:
        resp = await _get(f"{GAMMA_API_BASE}/markets", params={"condition_ids": condition_id})
        data = resp.json()
        if isinstance(data, dict):
            data = data.get("markets", data.get("data", []))
        if not isinstance(data, list) or not data:
            return None
        raw = data[0]

        closed = bool(raw.get("closed", False))
        if not closed:
            return None

        prices = raw.get("outcomePrices")
        if isinstance(prices, str):
            import json as _json
            try:
                prices = _json.loads(prices)
            except Exception:
                prices = []
        if not isinstance(prices, list) or len(prices) < 2:
            return None

        try:
            yes_price = float(prices[0])
        except (TypeError, ValueError):
            return None

        if yes_price >= 0.99:
            return "YES"
        if yes_price <= 0.01:
            return "NO"
        return None  # closed but not yet cleanly resolved to a binary outcome
    except Exception as e:
        log.debug("fetch_market_resolution_failed", condition_id=condition_id, error=str(e))
        return None


def compute_spread(orderbook: dict) -> float:
    """Bid/ask spread as a fraction of midpoint price. Returns 1.0 (max) if no book depth."""
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])
    if not bids or not asks:
        return 1.0
    try:
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
    except (KeyError, ValueError, TypeError, IndexError):
        return 1.0
    mid = (best_bid + best_ask) / 2
    if mid <= 0:
        return 1.0
    return abs(best_ask - best_bid) / mid


async def upsert_prediction_market(db: AsyncSession, raw: dict) -> PredictionMarket:
    """Idempotent upsert of a Gamma market payload into PredictionMarket, keyed on condition_id."""
    condition_id = str(raw.get("conditionId") or raw.get("condition_id") or raw.get("id") or "")
    if not condition_id:
        raise ValueError("market payload missing conditionId")

    result = await db.execute(
        select(PredictionMarket).where(PredictionMarket.polymarket_condition_id == condition_id)
    )
    market = result.scalar_one_or_none()

    yes_token_id, no_token_id = _parse_token_ids(raw)
    yes_price = _parse_yes_price(raw)

    expiry_raw = raw.get("endDate") or raw.get("end_date_iso")
    expiry_at = None
    if expiry_raw:
        try:
            expiry_at = datetime.fromisoformat(str(expiry_raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            expiry_at = None

    fields = dict(
        polymarket_slug=str(raw.get("slug", "")),
        question=str(raw.get("question", raw.get("title", ""))),
        category=str(raw.get("category") or (raw.get("tags") or [""])[0] if raw.get("tags") else raw.get("category", "")),
        outcomes=_parse_outcomes(raw),
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
        current_yes_price=yes_price,
        volume_24h=float(raw.get("volume24hr", raw.get("volume", 0)) or 0),
        liquidity=float(raw.get("liquidity", 0) or 0),
        expiry_at=expiry_at,
        last_scanned_at=datetime.utcnow(),
    )

    if market:
        for k, v in fields.items():
            setattr(market, k, v)
    else:
        market = PredictionMarket(
            id=str(uuid.uuid4()),
            polymarket_condition_id=condition_id,
            status="active",
            first_seen_at=datetime.utcnow(),
            **fields,
        )
        db.add(market)

    await db.commit()
    await db.refresh(market)
    return market
