"""
Captures Anthropic API usage from response objects and persists cost to DB.
Cost is calculated from published per-token pricing for each model.
"""
import uuid
from datetime import datetime
import structlog
from app.config import AVAILABLE_SIGNAL_MODELS
from app.db.session import AsyncSessionLocal
from app.db.models.api_usage import ApiUsage

log = structlog.get_logger()

# Build pricing lookup from config
_PRICING: dict[str, dict] = {
    m["id"]: {"input": m["input_cost_per_m"] / 1_000_000, "output": m["output_cost_per_m"] / 1_000_000}
    for m in AVAILABLE_SIGNAL_MODELS
}

# Episode review models may not be in AVAILABLE_SIGNAL_MODELS — add Sonnet fallback
_PRICING.setdefault("claude-sonnet-4-6", {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000})
_PRICING.setdefault("claude-haiku-4-5-20251001", {"input": 0.80 / 1_000_000, "output": 4.00 / 1_000_000})


def calculate_cost(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0) -> float:
    pricing = _PRICING.get(model, {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000})
    # Cache reads are billed at ~10% of normal input price
    cache_price = pricing["input"] * 0.1
    return (
        (input_tokens * pricing["input"])
        + (output_tokens * pricing["output"])
        + (cache_read_tokens * cache_price)
    )


async def track_usage(
    model: str,
    call_type: str,
    usage,           # Anthropic Usage object OR dict with input_tokens/output_tokens
    market: str = "all",
    episode_id: str | None = None,
) -> float:
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        cache_read_tokens = usage.get("cache_read_tokens", 0) or 0
    else:
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0

    cost = calculate_cost(model, input_tokens, output_tokens, cache_read_tokens)

    try:
        async with AsyncSessionLocal() as db:
            db.add(ApiUsage(
                id=str(uuid.uuid4()),
                model=model,
                call_type=call_type,
                market=market,
                episode_id=episode_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cost_usd=cost,
                created_at=datetime.utcnow(),
            ))
            await db.commit()
    except Exception as e:
        log.warning("cost_tracking_failed", error=str(e))

    log.debug("api_usage", model=model, call_type=call_type,
              input=input_tokens, output=output_tokens, cost_usd=round(cost, 6))
    return cost
