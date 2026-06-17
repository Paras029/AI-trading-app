"""
Settings & cost API — bot runtime config (risk gate thresholds, forecast role
weights/models, scanner filters), pause/resume, live-trading arm/disarm, and API spend
tracking.
"""
from datetime import datetime, timedelta
from typing import Literal
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.config import (
    AVAILABLE_FORECAST_MODELS, AVAILABLE_FORECAST_ROLES, RISK_GATE_DEFAULTS,
    DEFAULT_BOT_CONFIG, settings,
)
from app.core import redis_client
from app.db.models import ApiUsage
from app.services.ai import providers

router = APIRouter(prefix="/api/settings", tags=["settings"])
costs_router = APIRouter(prefix="/api/costs", tags=["costs"])

log = structlog.get_logger()

LIVE_ARM_CONFIRMATION_PHRASE = "I UNDERSTAND THE RISK"

# Keys editable via PUT /api/settings — every key in RISK_GATE_DEFAULTS plus the
# scanner/forecast/trading-mode config (NOT live_armed — that has its own dedicated,
# more conservative endpoint below; never allow it to be flipped on through this
# generic bulk-update path).
_ALLOWED_UPDATE_KEYS = set(RISK_GATE_DEFAULTS.keys()) | {
    "prediction_trading_mode",
    "forecast_role_weights",
    "forecast_role_models",
    "scan_interval_seconds",
    "scanner_categories",
    "scanner_min_volume",
    "scanner_max_expiry_days",
    "scanner_min_edge_pct",
    "min_edge_pct",
}


def _forecast_roles_with_key_status() -> list[dict]:
    roles = []
    for r in AVAILABLE_FORECAST_ROLES:
        roles.append({**r, "has_key": providers.has_key_for_provider(r["provider"])})
    return roles


def _forecast_models_with_key_status() -> list[dict]:
    models = []
    for m in AVAILABLE_FORECAST_MODELS:
        models.append({**m, "has_key": providers.has_key_for_provider(m["provider"])})
    return models


@router.get("")
async def get_settings():
    config = await redis_client.get_bot_config()
    return {
        "config": config,
        "forecast_roles": _forecast_roles_with_key_status(),
        "forecast_models": _forecast_models_with_key_status(),
    }


@router.put("")
async def update_settings(body: dict):
    updates = {k: v for k, v in body.items() if k in _ALLOWED_UPDATE_KEYS}

    if "prediction_trading_mode" in updates and updates["prediction_trading_mode"] not in ("paper", "live"):
        raise HTTPException(status_code=400, detail="prediction_trading_mode must be 'paper' or 'live'")

    if "forecast_role_models" in updates:
        valid_model_ids = {m["id"] for m in AVAILABLE_FORECAST_MODELS}
        for role, model_id in (updates["forecast_role_models"] or {}).items():
            if model_id not in valid_model_ids:
                raise HTTPException(status_code=400, detail=f"Unknown forecast model id: {model_id}")

    # Switching mode away from 'live' automatically disarms — never let a stale
    # live_armed=True linger once the operator has switched back to paper.
    if updates.get("prediction_trading_mode") == "paper":
        updates["live_armed"] = False

    updated = await redis_client.set_bot_config(updates)
    return {"config": updated}


@router.post("/arm-live")
async def arm_live(body: dict):
    """
    Second of the two independent gates required for live execution (the first being
    prediction_trading_mode=='live', checked separately by risk_agent.py and
    polymarket_live.py). Requires the exact confirmation phrase, case-sensitive, with no
    trimming beyond a single strip() — this is deliberately unforgiving.
    """
    confirmation = str(body.get("confirmation", ""))
    if confirmation.strip() != LIVE_ARM_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation phrase must be exactly: \"{LIVE_ARM_CONFIRMATION_PHRASE}\"",
        )

    bot_config = await redis_client.get_bot_config()
    if bot_config.get("prediction_trading_mode") != "live":
        raise HTTPException(
            status_code=400,
            detail="Set prediction_trading_mode to 'live' before arming. Arming alone does not enable live trading.",
        )

    if not settings.polymarket_private_key or not settings.polymarket_funder_address:
        raise HTTPException(
            status_code=400,
            detail="POLYMARKET_PRIVATE_KEY / POLYMARKET_FUNDER_ADDRESS are not configured in the backend environment.",
        )

    updated = await redis_client.set_bot_config({"live_armed": True})
    log.warning("live_trading_armed", confirmed_by="operator")
    return {"live_armed": True, "config": updated}


@router.post("/disarm-live")
async def disarm_live():
    updated = await redis_client.set_bot_config({"live_armed": False})
    log.info("live_trading_disarmed")
    return {"live_armed": False, "config": updated}


@router.post("/pause")
async def pause_bot():
    await redis_client.set_bot_paused(True)
    return {"paused": True, "message": "Bot paused — kill_switch gate now fails closed for all signals."}


@router.post("/resume")
async def resume_bot():
    await redis_client.set_bot_paused(False)
    return {"paused": False, "message": "Bot resumed."}


@router.get("/status")
async def bot_status():
    paused = await redis_client.is_bot_paused()
    return {"paused": paused}


@costs_router.get("")
async def get_costs(
    period: Literal["today", "week", "all"] = Query("today"),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    if period == "today":
        since = now - timedelta(hours=24)
    elif period == "week":
        since = now - timedelta(days=7)
    else:
        since = datetime(2000, 1, 1)

    total_result = await db.execute(
        select(func.sum(ApiUsage.cost_usd), func.count(ApiUsage.id))
        .where(ApiUsage.created_at >= since)
    )
    total_cost, total_calls = total_result.one()
    total_cost = float(total_cost or 0.0)
    total_calls = int(total_calls or 0)

    by_model_result = await db.execute(
        select(ApiUsage.model, func.sum(ApiUsage.cost_usd), func.count(ApiUsage.id))
        .where(ApiUsage.created_at >= since)
        .group_by(ApiUsage.model)
        .order_by(func.sum(ApiUsage.cost_usd).desc())
    )
    by_model = [
        {"model": r[0], "cost_usd": float(r[1] or 0), "calls": int(r[2] or 0)}
        for r in by_model_result
    ]

    by_type_result = await db.execute(
        select(ApiUsage.call_type, func.sum(ApiUsage.cost_usd), func.count(ApiUsage.id))
        .where(ApiUsage.created_at >= since)
        .group_by(ApiUsage.call_type)
        .order_by(func.sum(ApiUsage.cost_usd).desc())
    )
    by_call_type = [
        {"call_type": r[0], "cost_usd": float(r[1] or 0), "calls": int(r[2] or 0)}
        for r in by_type_result
    ]

    by_market_result = await db.execute(
        select(ApiUsage.market, func.sum(ApiUsage.cost_usd), func.count(ApiUsage.id))
        .where(ApiUsage.created_at >= since)
        .group_by(ApiUsage.market)
        .order_by(func.sum(ApiUsage.cost_usd).desc())
    )
    by_market = [
        {"market": r[0], "cost_usd": float(r[1] or 0), "calls": int(r[2] or 0)}
        for r in by_market_result
    ]

    return {
        "period": period,
        "total_usd": total_cost,
        "total_calls": total_calls,
        "by_model": by_model,
        "by_call_type": by_call_type,
        "by_market": by_market,
    }
