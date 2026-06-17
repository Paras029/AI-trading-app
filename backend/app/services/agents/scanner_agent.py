"""
Scanner Agent — Stage 1 of the pipeline. Pulls live Polymarket markets, applies a cheap
filter chain (no AI calls), and writes one MarketScan row per market evaluated. Markets
that pass move to status='scanned' and become eligible for the Research Agent.

Conceptually replaces the old indicators/engine.py::should_call_llm() pre-filter — a cheap
gate before spending AI tokens, applied to market selection instead of indicator thresholds.
"""
import uuid
from datetime import datetime, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import MarketScan, PredictionMarket
from app.core import redis_client
from app.services.market_data import polymarket

log = structlog.get_logger()

DEFAULT_FILTERS = {
    "categories": ["politics", "crypto", "sports", "pop-culture"],
    "min_volume": 5000,
    "max_expiry_days": 30,
    "min_edge_pct": 0.05,
}


def _days_to_expiry(expiry_at) -> float:
    if not expiry_at:
        return 999.0
    now = datetime.utcnow()
    delta = expiry_at - now
    return max(delta.total_seconds() / 86400.0, 0.0)


async def _evaluate_market(db: AsyncSession, raw: dict, filters: dict) -> MarketScan:
    """Upsert the market, run the filter chain, persist + return a MarketScan row."""
    market = await polymarket.upsert_prediction_market(db, raw)

    price = market.current_yes_price
    volume = market.volume_24h
    days_left = _days_to_expiry(market.expiry_at)
    naive_edge_pct = abs(0.5 - price)

    flags: dict = {}
    reject_reason = ""
    passed = True

    if volume < filters.get("min_volume", DEFAULT_FILTERS["min_volume"]):
        passed = False
        reject_reason = "volume_too_low"
        flags["min_volume"] = False
    elif days_left > filters.get("max_expiry_days", DEFAULT_FILTERS["max_expiry_days"]):
        passed = False
        reject_reason = "expiry_too_far"
        flags["max_expiry_days"] = False
    elif naive_edge_pct < filters.get("min_edge_pct", DEFAULT_FILTERS["min_edge_pct"]):
        passed = False
        reject_reason = "naive_edge_too_small"
        flags["min_edge_pct"] = False

    spread = 0.0
    if passed:
        orderbook = await polymarket.fetch_orderbook(market.yes_token_id)
        spread = polymarket.compute_spread(orderbook)
        if spread > 0.10:
            passed = False
            reject_reason = "wide_spread"
            flags["wide_spread"] = True

    if passed:
        history = await polymarket.fetch_market_history(market.polymarket_condition_id)
        if len(history) >= 2:
            try:
                first_p = float(history[0]["p"])
                last_p = float(history[-1]["p"])
                price_move = abs(last_p - first_p)
                if price_move > 0.20:
                    flags["vol_spike"] = True
                    flags["price_move"] = round(price_move, 4)
            except (TypeError, ValueError, KeyError):
                pass

    scan = MarketScan(
        id=str(uuid.uuid4()),
        market_id=market.id,
        scanned_at=datetime.utcnow(),
        passed=passed,
        reject_reason=reject_reason,
        price_at_scan=price,
        volume_at_scan=volume,
        spread_at_scan=spread,
        days_to_expiry=days_left,
        naive_edge_pct=naive_edge_pct,
        flags=flags,
    )
    db.add(scan)

    if passed:
        market.status = "scanned"
    elif market.status == "active":
        market.status = "rejected"
    market.last_scanned_at = datetime.utcnow()

    await db.commit()

    await redis_client.publish("scanner:activity", {
        "ts": datetime.utcnow().isoformat(),
        "market_id": market.id,
        "question": market.question,
        "message": (
            f"PASSED — vol ${volume:,.0f}, edge {naive_edge_pct:.1%}, spread {spread:.1%}"
            if passed else f"rejected: {reject_reason}"
        ),
        "passed": passed,
    })

    return scan


async def scan_markets(db: AsyncSession, filters: dict) -> list[MarketScan]:
    """
    1. fetch_markets() per category.
    2. upsert_prediction_market(), then filter chain: min_volume, max_expiry_days,
       min_edge_pct (naive proxy), wide_spread, vol_spike/price_move.
    3. Writes one MarketScan row per market (pass or reject + reason + flags).
    4. Publishes via redis_client.publish('scanner:activity', {...}).
    5. Returns passed=True rows for hand-off to Research.
    """
    merged_filters = {**DEFAULT_FILTERS, **(filters or {})}
    categories = merged_filters.get("categories") or DEFAULT_FILTERS["categories"]

    all_raw: list[dict] = []
    for category in categories:
        raw_markets = await polymarket.fetch_markets(category=category, limit=100)
        all_raw.extend(raw_markets)

    # De-duplicate by conditionId in case categories overlap
    seen: set[str] = set()
    deduped: list[dict] = []
    for raw in all_raw:
        cid = str(raw.get("conditionId") or raw.get("condition_id") or raw.get("id") or "")
        if cid and cid not in seen:
            seen.add(cid)
            deduped.append(raw)

    await redis_client.publish("scanner:activity", {
        "ts": datetime.utcnow().isoformat(),
        "message": f"Scanning {len(deduped)} markets across {len(categories)} categories...",
    })

    scans: list[MarketScan] = []
    for raw in deduped:
        try:
            scan = await _evaluate_market(db, raw, merged_filters)
            scans.append(scan)
        except Exception as e:
            log.error("scan_market_failed", error=str(e))

    passed_scans = [s for s in scans if s.passed]
    log.info("scan_complete", total=len(scans), passed=len(passed_scans))
    return passed_scans


async def run_manual_scan(db: AsyncSession, filters: dict) -> dict:
    """Same path as scan_markets(), invoked synchronously for the 'Scan Now' button."""
    passed_scans = await scan_markets(db, filters)
    return {
        "scanned_count": len(passed_scans),
        "passed_market_ids": [s.market_id for s in passed_scans],
    }
