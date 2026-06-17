"""
Prediction Agent's ensemble fan-out: calls each forecast role (filtered to roles with a
configured API key, weights renormalized proportionally), persists one ModelForecast row
per role (including skipped_no_key rows for UI transparency), aggregates into a single
ensemble probability, optionally blends with the XGBoost model, and computes the final
trade signal/action.

FORECAST_ROLES defaults are sourced from config.AVAILABLE_FORECAST_ROLES — the source of
truth the Settings UI renders from — not hardcoded here.
"""
import asyncio
import uuid
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings, AVAILABLE_FORECAST_ROLES
from app.db.models import ModelForecast, PredictionMarket, ResearchBrief
from app.core import redis_client
from app.services.ai import providers
from app.services.ai.prompt_builder import FORECASTER_SYSTEM_PROMPTS, build_forecast_prompt
from app.services.prediction import calibration

log = structlog.get_logger()

# Default role/provider/model/weight config — mirrors config.AVAILABLE_FORECAST_ROLES.
# bot_config['forecast_role_weights'] / ['forecast_role_models'] (Redis) override these
# at call time; AVAILABLE_FORECAST_ROLES remains the schema/source-of-truth for the UI.
FORECAST_ROLES = [
    {
        "role": r["role"],
        "provider": r["provider"],
        "model": r["default_model"],
        "weight": r["default_weight"],
    }
    for r in AVAILABLE_FORECAST_ROLES
]


async def _resolve_role_configs(bot_config: dict) -> list[dict]:
    """Apply Redis-configured weight/model overrides on top of AVAILABLE_FORECAST_ROLES."""
    weights = bot_config.get("forecast_role_weights", {})
    models = bot_config.get("forecast_role_models", {})
    resolved = []
    for role_def in FORECAST_ROLES:
        role = role_def["role"]
        resolved.append({
            "role": role,
            "provider": role_def["provider"],
            "model": models.get(role, role_def["model"]),
            "weight": float(weights.get(role, role_def["weight"])),
        })
    return resolved


async def run_ensemble(db: AsyncSession, market: PredictionMarket, brief: ResearchBrief | None) -> list[ModelForecast]:
    """
    1. available = roles with providers.has_key_for_provider(role['provider'])
    2. renormalize weights proportionally across available roles.
    3. asyncio.gather over available roles calling providers.call_role() with that role's
       persona prompt.
    4. Persist one ModelForecast row per role, INCLUDING skipped_no_key rows.
    """
    bot_config = await redis_client.get_bot_config()
    role_configs = await _resolve_role_configs(bot_config)

    available = [r for r in role_configs if providers.has_key_for_provider(r["provider"])]
    unavailable = [r for r in role_configs if r not in available]

    total_available_weight = sum(r["weight"] for r in available) or 1.0
    for r in available:
        r["weight_applied"] = r["weight"] / total_available_weight
    for r in unavailable:
        r["weight_applied"] = 0.0

    market_dict = {
        "question": market.question,
        "category": market.category,
        "current_yes_price": market.current_yes_price,
        "expiry_at": market.expiry_at.isoformat() if market.expiry_at else None,
    }
    brief_dict = None
    if brief is not None:
        brief_dict = {
            "brief_text": brief.brief_text,
            "bullish_pct": brief.bullish_pct * 100,
            "bearish_pct": brief.bearish_pct * 100,
            "neutral_pct": brief.neutral_pct * 100,
            "narrative_probability": brief.narrative_probability,
            "source_agreement_pct": brief.source_agreement_pct * 100,
        }
    user_prompt = build_forecast_prompt(market_dict, brief_dict)

    async def _call_one(role_cfg: dict) -> dict:
        system_prompt = FORECASTER_SYSTEM_PROMPTS.get(role_cfg["role"], FORECASTER_SYSTEM_PROMPTS["primary_forecaster"])
        await redis_client.publish("prediction:activity", {
            "market_id": market.id,
            "role": role_cfg["role"],
            "provider": role_cfg["provider"],
            "model": role_cfg["model"],
            "status": "thinking",
        })
        result = await providers.call_role(role_cfg, system_prompt, user_prompt)
        await redis_client.publish("prediction:activity", {
            "market_id": market.id,
            "role": role_cfg["role"],
            "provider": role_cfg["provider"],
            "model": role_cfg["model"],
            "status": result["status"],
            "probability": result.get("probability"),
            "reasoning": result.get("reasoning"),
        })
        return result

    results = await asyncio.gather(*[_call_one(r) for r in available], return_exceptions=True)

    forecasts: list[ModelForecast] = []
    for role_cfg, result in zip(available, results):
        if isinstance(result, BaseException):
            log.error("ensemble_role_call_failed", role=role_cfg["role"], error=str(result))
            result = {"probability": None, "reasoning": None, "status": "error",
                      "latency_ms": 0, "error_detail": str(result)[:500]}
        forecasts.append(ModelForecast(
            id=str(uuid.uuid4()),
            market_id=market.id,
            signal_id=None,
            role=role_cfg["role"],
            provider=role_cfg["provider"],
            model=role_cfg["model"],
            probability=result.get("probability") or 0.0,
            reasoning=result.get("reasoning") or "",
            weight_configured=role_cfg["weight"],
            weight_applied=role_cfg["weight_applied"] if result.get("status") == "ok" else 0.0,
            latency_ms=result.get("latency_ms", 0),
            status=result.get("status", "error"),
            error_detail=result.get("error_detail", ""),
            created_at=datetime.utcnow(),
        ))

    for role_cfg in unavailable:
        forecasts.append(ModelForecast(
            id=str(uuid.uuid4()),
            market_id=market.id,
            signal_id=None,
            role=role_cfg["role"],
            provider=role_cfg["provider"],
            model=role_cfg["model"],
            probability=0.0,
            reasoning="",
            weight_configured=role_cfg["weight"],
            weight_applied=0.0,
            latency_ms=0,
            status="skipped_no_key",
            error_detail="",
            created_at=datetime.utcnow(),
        ))
        await redis_client.publish("prediction:activity", {
            "market_id": market.id,
            "role": role_cfg["role"],
            "provider": role_cfg["provider"],
            "model": role_cfg["model"],
            "status": "skipped_no_key",
        })

    for f in forecasts:
        db.add(f)
    await db.commit()
    for f in forecasts:
        await db.refresh(f)

    return forecasts


def aggregate(forecasts: list) -> float:
    """Weighted average of probability using weight_applied, status=='ok' only."""
    ok_forecasts = [f for f in forecasts if getattr(f, "status", None) == "ok" and getattr(f, "probability", None) is not None]
    total_weight = sum(getattr(f, "weight_applied", 0.0) for f in ok_forecasts)
    if total_weight <= 0:
        # No successful forecasts — neutral fallback
        return 0.5
    return sum(f.probability * f.weight_applied for f in ok_forecasts) / total_weight


async def blend_with_xgboost(db: AsyncSession, ensemble_prob: float, features: dict) -> tuple[float, bool]:
    """
    Cold-start guard: if settled-trade count < xgboost_min_samples, return
    (ensemble_prob, False) unchanged. Else load persisted model, predict, blend.
    """
    from sqlalchemy import select, func
    from app.db.models import Trade

    result = await db.execute(
        select(func.count(Trade.id)).where(Trade.status.in_(["settled_win", "settled_loss"]))
    )
    settled_count = int(result.scalar() or 0)

    if settled_count < settings.xgboost_min_samples:
        return ensemble_prob, False

    model = await calibration.load_model()
    if model is None:
        return ensemble_prob, False

    try:
        feature_keys = ["sentiment_score", "volume_delta", "source_agreement", "time_decay", "volatility", "spread_width"]
        row = [[float(features.get(k, 0.0) or 0.0) for k in feature_keys] + [ensemble_prob]]
        xgb_prob = float(model.predict_proba(row)[0][1])
        blended = (ensemble_prob + xgb_prob) / 2.0
        return blended, True
    except Exception as e:
        log.warning("xgboost_blend_failed", error=str(e))
        return ensemble_prob, False


def compute_signal(final_prob: float, market_price: float, edge_threshold: float) -> dict:
    """edge = final_prob - market_price; action thresholds per the plan."""
    edge = final_prob - market_price
    if edge > edge_threshold:
        action = "BUY_YES"
    elif edge < -edge_threshold:
        action = "BUY_NO"
    elif abs(edge) > edge_threshold / 2:
        action = "WATCH"
    else:
        action = "SKIP"

    # Expected value of a $1 stake: YES side wins (1-price)/price per share if correct,
    # loses stake if wrong; NO side is symmetric. Use the side implied by the edge sign.
    if edge >= 0:
        p_win = final_prob
        payout_per_dollar = (1 - market_price) / market_price if market_price > 0 else 0.0
    else:
        p_win = 1 - final_prob
        no_price = 1 - market_price
        payout_per_dollar = (1 - no_price) / no_price if no_price > 0 else 0.0
    expected_value = p_win * payout_per_dollar - (1 - p_win)

    return {
        "edge": round(edge, 4),
        "action": action,
        "expected_value": round(expected_value, 4),
    }
