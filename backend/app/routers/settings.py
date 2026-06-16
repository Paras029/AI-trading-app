"""
Settings & cost API — model selection, prompt depth, API spend tracking.
"""
from datetime import datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.config import AVAILABLE_SIGNAL_MODELS, PROMPT_DEPTH_CONFIG, DEFAULT_BOT_CONFIG, settings
from app.core import redis_client
from app.db.models import ApiUsage
from app.services.market_hours import market_status_all

router = APIRouter(prefix="/api/settings", tags=["settings"])
costs_router = APIRouter(prefix="/api/costs", tags=["costs"])

_PROMPT_DEPTHS = [
    {
        "id": "compact",
        "label": "Compact",
        "description": "3 candles · 2 headlines · Fastest & cheapest",
        **PROMPT_DEPTH_CONFIG["compact"],
    },
    {
        "id": "standard",
        "label": "Standard",
        "description": "5 candles · 3 headlines · Balanced",
        **PROMPT_DEPTH_CONFIG["standard"],
    },
    {
        "id": "rich",
        "label": "Rich",
        "description": "10 candles · 5 headlines · Most context, highest cost",
        **PROMPT_DEPTH_CONFIG["rich"],
    },
]


@router.get("")
async def get_settings():
    config = await redis_client.get_bot_config()
    return {
        "config": config,
        "available_models": AVAILABLE_SIGNAL_MODELS,
        "prompt_depths": _PROMPT_DEPTHS,
    }


@router.put("")
async def update_settings(body: dict):
    allowed_keys = {"signal_model", "prompt_depth"}
    updates = {k: v for k, v in body.items() if k in allowed_keys}

    # Validate model id
    if "signal_model" in updates:
        valid_ids = {m["id"] for m in AVAILABLE_SIGNAL_MODELS}
        if updates["signal_model"] not in valid_ids:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Unknown model id: {updates['signal_model']}")

    # Validate depth
    if "prompt_depth" in updates:
        if updates["prompt_depth"] not in PROMPT_DEPTH_CONFIG:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Unknown depth: {updates['prompt_depth']}")

    updated = await redis_client.set_bot_config(updates)
    return {"config": updated}


@router.post("/pause")
async def pause_bot():
    await redis_client.set_bot_paused(True)
    return {"paused": True, "message": "Signal generation paused. SL/TP monitoring continues."}


@router.post("/resume")
async def resume_bot():
    await redis_client.set_bot_paused(False)
    return {"paused": False, "message": "Bot resumed."}


@router.get("/status")
async def bot_status():
    paused = await redis_client.is_bot_paused()
    return {
        "paused": paused,
        "market_hours": market_status_all(),
    }


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

    base = select(ApiUsage).where(ApiUsage.created_at >= since)

    # Total cost
    total_result = await db.execute(
        select(func.sum(ApiUsage.cost_usd), func.count(ApiUsage.id))
        .where(ApiUsage.created_at >= since)
    )
    total_cost, total_calls = total_result.one()
    total_cost = float(total_cost or 0.0)
    total_calls = int(total_calls or 0)

    # By model
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

    # By call type
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

    # By market
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
