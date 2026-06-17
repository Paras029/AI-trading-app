"""
XGBoost ensemble-blending model: trains on settled trades' feature snapshots + ensemble
probability to predict win/loss, then blends its output with the raw LLM-ensemble
probability once enough settled trades exist (cold-start guard, see
prediction/ensemble.py::blend_with_xgboost).

Training is triggered by the post-mortem agent on a schedule (every
xgboost_retrain_interval settlements), fire-and-forget — never inline in the
settlement/risk request path.
"""
import os
import time
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Trade, PredictionSignal

log = structlog.get_logger()

MODEL_PATH = "models/xgboost_prediction_blend.json"

_model_cache = None
_model_cache_mtime: float | None = None
_last_train_time: float = 0.0
_MIN_RETRAIN_INTERVAL_SECONDS = 3600  # capped at once/hour


def compute_brier_score(predictions: list[float], outcomes: list[float]) -> float:
    """mean((p - o)^2) — lower is better, 0 is perfect calibration."""
    if not predictions or len(predictions) != len(outcomes):
        return 0.0
    n = len(predictions)
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / n


async def load_model():
    """Returns the persisted XGBClassifier, or None if MODEL_PATH is absent (cold start)."""
    global _model_cache, _model_cache_mtime
    if not os.path.exists(MODEL_PATH):
        return None
    try:
        mtime = os.path.getmtime(MODEL_PATH)
        if _model_cache is not None and _model_cache_mtime == mtime:
            return _model_cache

        import xgboost as xgb
        model = xgb.XGBClassifier()
        model.load_model(MODEL_PATH)
        _model_cache = model
        _model_cache_mtime = mtime
        return model
    except Exception as e:
        log.warning("xgboost_load_failed", error=str(e))
        return None


async def train_or_update_model(db: AsyncSession) -> None:
    """
    Pulls settled Trade rows joined to PredictionSignal.feature_snapshot +
    ensemble_probability, labels = win/loss, trains/updates an XGBClassifier,
    saves to MODEL_PATH. Capped at once per hour even if called more frequently.
    """
    global _last_train_time
    now = time.monotonic()
    if now - _last_train_time < _MIN_RETRAIN_INTERVAL_SECONDS:
        log.debug("xgboost_retrain_skipped_rate_limited")
        return
    _last_train_time = now

    try:
        import xgboost as xgb
    except ImportError:
        log.warning("xgboost_not_installed_skipping_train")
        return

    result = await db.execute(
        select(Trade, PredictionSignal)
        .join(PredictionSignal, Trade.signal_id == PredictionSignal.id)
        .where(Trade.status.in_(["settled_win", "settled_loss"]))
    )
    rows = result.all()

    if len(rows) < 10:
        log.info("xgboost_train_skipped_insufficient_data", count=len(rows))
        return

    feature_keys = ["sentiment_score", "volume_delta", "source_agreement", "time_decay", "volatility", "spread_width"]
    X = []
    y = []
    for trade, signal in rows:
        snapshot = signal.feature_snapshot or {}
        if not snapshot:
            continue
        row = [float(snapshot.get(k, 0.0) or 0.0) for k in feature_keys]
        row.append(float(signal.ensemble_probability or 0.5))
        X.append(row)
        y.append(1 if trade.status == "settled_win" else 0)

    if len(X) < 10 or len(set(y)) < 2:
        log.info("xgboost_train_skipped_insufficient_labeled_data", count=len(X))
        return

    model = xgb.XGBClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        objective="binary:logistic",
        eval_metric="logloss",
    )
    model.fit(X, y)

    os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
    model.save_model(MODEL_PATH)
    log.info("xgboost_model_trained", samples=len(X))

    global _model_cache, _model_cache_mtime
    _model_cache = model
    _model_cache_mtime = os.path.getmtime(MODEL_PATH)
