"""
Feature engineering for the XGBoost blend layer. Builds a flat numeric feature vector
from a market + research brief + ensemble forecasts, consumed by prediction/ensemble.py
(at inference time) and prediction/calibration.py (at training time, pulled back out of
PredictionSignal.feature_snapshot).
"""
from __future__ import annotations


def build_feature_vector(market, brief, forecasts: list[dict]) -> dict:
    """
    market: PredictionMarket (or dict with the same fields)
    brief: ResearchBrief (or dict with the same fields), may be None
    forecasts: list of dicts with at least {probability, weight_applied, status}
    """
    def _get(obj, key, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    sentiment_score = (_get(brief, "bullish_pct", 0.0) or 0.0) - (_get(brief, "bearish_pct", 0.0) or 0.0)
    source_agreement = _get(brief, "source_agreement_pct", 0.0) or 0.0

    expiry_at = _get(market, "expiry_at", None)
    time_decay = 0.5
    if expiry_at is not None:
        try:
            from datetime import datetime
            now = datetime.utcnow()
            days_left = max((expiry_at - now).total_seconds() / 86400.0, 0.0)
            # Normalize: 0 days left -> 1.0 (urgent), 60+ days left -> ~0.0
            time_decay = max(0.0, 1.0 - min(days_left, 60.0) / 60.0)
        except Exception:
            time_decay = 0.5

    ok_probs = [f.get("probability") for f in forecasts if f.get("status") == "ok" and f.get("probability") is not None]
    if len(ok_probs) >= 2:
        mean_p = sum(ok_probs) / len(ok_probs)
        volatility = (sum((p - mean_p) ** 2 for p in ok_probs) / len(ok_probs)) ** 0.5
    else:
        volatility = 0.0

    volume_24h = _get(market, "volume_24h", 0.0) or 0.0
    liquidity = _get(market, "liquidity", 0.0) or 0.0
    volume_delta = volume_24h / liquidity if liquidity > 0 else 0.0

    spread_width = _get(market, "_spread", None)
    if spread_width is None:
        spread_width = 0.02  # default placeholder if caller didn't attach a live spread

    return {
        "sentiment_score": round(sentiment_score, 4),
        "volume_delta": round(volume_delta, 4),
        "source_agreement": round(source_agreement, 4),
        "time_decay": round(time_decay, 4),
        "volatility": round(volatility, 4),
        "spread_width": round(spread_width, 4),
    }
