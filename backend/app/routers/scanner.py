"""
Scanner API — filter config (read/write via Redis bot:config) + recent scan log +
manual on-demand scan trigger ("Scan Now" button).
"""
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.db.models import MarketScan, PredictionMarket
from app.core import redis_client
from app.schemas.common import MarketScanOut
from app.services.agents import scanner_agent

log = structlog.get_logger()
router = APIRouter(prefix="/api/scanner", tags=["scanner"])


@router.get("/filters")
async def get_filters():
    bot_config = await redis_client.get_bot_config()
    return {
        "categories": bot_config.get("scanner_categories", scanner_agent.DEFAULT_FILTERS["categories"]),
        "min_volume": bot_config.get("scanner_min_volume", scanner_agent.DEFAULT_FILTERS["min_volume"]),
        "max_expiry_days": bot_config.get("scanner_max_expiry_days", scanner_agent.DEFAULT_FILTERS["max_expiry_days"]),
        "min_edge_pct": bot_config.get("scanner_min_edge_pct", scanner_agent.DEFAULT_FILTERS["min_edge_pct"]),
    }


@router.put("/filters")
async def update_filters(body: dict):
    allowed_keys = {
        "scanner_categories": "categories",
        "scanner_min_volume": "min_volume",
        "scanner_max_expiry_days": "max_expiry_days",
        "scanner_min_edge_pct": "min_edge_pct",
    }
    # Accept either the bot_config key names or the bare filter names from the UI.
    updates: dict = {}
    for config_key, bare_key in allowed_keys.items():
        if config_key in body:
            updates[config_key] = body[config_key]
        elif bare_key in body:
            updates[config_key] = body[bare_key]

    updated = await redis_client.set_bot_config(updates)
    return {
        "categories": updated.get("scanner_categories"),
        "min_volume": updated.get("scanner_min_volume"),
        "max_expiry_days": updated.get("scanner_max_expiry_days"),
        "min_edge_pct": updated.get("scanner_min_edge_pct"),
    }


@router.get("/scans", response_model=list[MarketScanOut])
async def get_scans(
    limit: int = Query(default=50, le=200),
    passed_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(MarketScan)
    if passed_only:
        q = q.where(MarketScan.passed == True)
    q = q.order_by(MarketScan.scanned_at.desc()).limit(limit)
    result = await db.execute(q)
    return [MarketScanOut.model_validate(s) for s in result.scalars()]


@router.post("/scan-now")
async def scan_now(db: AsyncSession = Depends(get_db)):
    bot_config = await redis_client.get_bot_config()
    filters = {
        "categories": bot_config.get("scanner_categories", scanner_agent.DEFAULT_FILTERS["categories"]),
        "min_volume": bot_config.get("scanner_min_volume", scanner_agent.DEFAULT_FILTERS["min_volume"]),
        "max_expiry_days": bot_config.get("scanner_max_expiry_days", scanner_agent.DEFAULT_FILTERS["max_expiry_days"]),
        "min_edge_pct": bot_config.get("scanner_min_edge_pct", scanner_agent.DEFAULT_FILTERS["min_edge_pct"]),
    }
    result = await scanner_agent.run_manual_scan(db, filters)
    return result


@router.get("/markets")
async def get_markets(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Lists cached PredictionMarket rows — used by the scanner UI to show what's currently
    in each pipeline stage without re-deriving it from MarketScan rows."""
    q = select(PredictionMarket)
    if status:
        q = q.where(PredictionMarket.status == status)
    q = q.order_by(PredictionMarket.last_scanned_at.desc()).limit(limit)
    result = await db.execute(q)
    markets = list(result.scalars())
    return [
        {
            "id": m.id,
            "polymarket_condition_id": m.polymarket_condition_id,
            "polymarket_slug": m.polymarket_slug,
            "question": m.question,
            "category": m.category,
            "outcomes": m.outcomes,
            "current_yes_price": m.current_yes_price,
            "volume_24h": m.volume_24h,
            "liquidity": m.liquidity,
            "expiry_at": m.expiry_at.isoformat() if m.expiry_at else None,
            "status": m.status,
            "resolved_outcome": m.resolved_outcome,
            "resolved_at": m.resolved_at.isoformat() if m.resolved_at else None,
            "first_seen_at": m.first_seen_at.isoformat() if m.first_seen_at else None,
            "last_scanned_at": m.last_scanned_at.isoformat() if m.last_scanned_at else None,
        }
        for m in markets
    ]
