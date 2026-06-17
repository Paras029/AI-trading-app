"""
9-gate risk evaluation, fixed order, kill switch first. Replaces risk.py::check_signal.
Always persists all 9 RiskGateCheck rows per signal evaluation, even when a short-circuit
(kill switch active) forces the rest to passed=False/skipped.
"""
import uuid
from datetime import datetime, timedelta
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import RiskGateCheck, Trade, PredictionSignal, PredictionMarket
from app.core import redis_client
from app.services.market_data import polymarket
from app.services.risk import kelly

log = structlog.get_logger()

GATE_SEQUENCE = [
    "kill_switch",
    "edge_threshold",
    "position_size_pct",
    "single_position_cap",
    "total_exposure_pct",
    "position_count",
    "max_drawdown",
    "daily_loss_limit",
    "slippage_check",
]


async def _check_daily_loss_limit(db: AsyncSession, portfolio, limit_pct: float) -> tuple[bool, float, float]:
    """Reuses the SQL pattern from risk.py::check_daily_loss_limit verbatim, scoped to Portfolio.
    Returns (within_limit, daily_pnl, threshold)."""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(func.sum(Trade.pnl)).where(
            Trade.portfolio_id == portfolio.id,
            Trade.settled_at >= since,
            Trade.status.in_(["settled_win", "settled_loss"]),
        )
    )
    daily_pnl = float(result.scalar() or 0.0)
    threshold = portfolio.total_equity * limit_pct
    within_limit = daily_pnl >= -threshold
    return within_limit, daily_pnl, threshold


async def evaluate_gates(db: AsyncSession, signal: PredictionSignal, portfolio, bot_config: dict) -> list[RiskGateCheck]:
    """
    Gate 1 reuses redis_client.is_bot_paused() verbatim — failing it short-circuits ALL
    subsequent gates to passed=False/skipped. Gates 2-9 are threshold checks against
    bot_config. Always persists all 9 rows. Publishes each gate result to
    redis_client.publish('risk:activity', {...}) as evaluated.
    """
    checks: list[RiskGateCheck] = []
    short_circuited = False

    market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == signal.market_id))
    market = market_result.scalar_one_or_none()

    # Pre-compute values needed by multiple gates
    side = "BUY_YES" if signal.action == "BUY_YES" else "BUY_NO"
    full_kelly = kelly.kelly_fraction_full(signal.final_probability, signal.market_price, side)
    kelly_multiplier = float(bot_config.get("kelly_multiplier", 0.25))
    single_cap = float(bot_config.get("single_position_cap_usd", 100.0))
    proposed_stake = kelly.kelly_stake(full_kelly, kelly_multiplier, portfolio.total_equity, single_cap)

    open_positions_result = await db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id, Trade.status == "open")
    )
    open_positions = list(open_positions_result.scalars())
    total_exposure = sum(t.stake_usdc for t in open_positions)

    for seq, gate_name in enumerate(GATE_SEQUENCE, start=1):
        passed = False
        threshold_value = 0.0
        actual_value = 0.0
        detail = ""

        if short_circuited:
            passed = False
            detail = "skipped: kill_switch active"
        elif gate_name == "kill_switch":
            paused = await redis_client.is_bot_paused()
            passed = not paused
            threshold_value = 0.0
            actual_value = 1.0 if paused else 0.0
            detail = "bot is paused" if paused else "bot is active"
            if not passed:
                short_circuited = True

        elif gate_name == "edge_threshold":
            min_edge = float(bot_config.get("min_edge_pct", 0.05))
            actual_value = abs(signal.edge)
            threshold_value = min_edge
            passed = actual_value >= min_edge
            detail = f"|edge|={actual_value:.4f} vs min {min_edge:.4f}"

        elif gate_name == "position_size_pct":
            max_pct = float(bot_config.get("max_position_pct", 0.05))
            actual_value = (proposed_stake / portfolio.total_equity) if portfolio.total_equity > 0 else 1.0
            threshold_value = max_pct
            passed = actual_value <= max_pct
            detail = f"stake {actual_value:.4f} of equity vs max {max_pct:.4f}"

        elif gate_name == "single_position_cap":
            actual_value = proposed_stake
            threshold_value = single_cap
            passed = proposed_stake <= single_cap
            detail = f"stake ${actual_value:.2f} vs cap ${threshold_value:.2f}"

        elif gate_name == "total_exposure_pct":
            max_total_pct = float(bot_config.get("max_total_exposure_pct", 0.40))
            projected_exposure = total_exposure + proposed_stake
            actual_value = (projected_exposure / portfolio.total_equity) if portfolio.total_equity > 0 else 1.0
            threshold_value = max_total_pct
            passed = actual_value <= max_total_pct
            detail = f"projected exposure {actual_value:.4f} vs max {max_total_pct:.4f}"

        elif gate_name == "position_count":
            max_positions = int(bot_config.get("max_concurrent_positions", 8))
            actual_value = len(open_positions)
            threshold_value = max_positions
            passed = actual_value < max_positions
            detail = f"{int(actual_value)} open vs max {max_positions}"

        elif gate_name == "max_drawdown":
            max_dd = float(bot_config.get("max_drawdown_pct", 0.25))
            if portfolio.peak_equity > 0:
                drawdown = (portfolio.peak_equity - portfolio.total_equity) / portfolio.peak_equity
            else:
                drawdown = 0.0
            actual_value = drawdown
            threshold_value = max_dd
            passed = drawdown <= max_dd
            detail = f"drawdown {actual_value:.4f} vs max {threshold_value:.4f}"

        elif gate_name == "daily_loss_limit":
            limit_pct = float(bot_config.get("daily_loss_limit_pct", 0.10))
            within_limit, daily_pnl, dd_threshold = await _check_daily_loss_limit(db, portfolio, limit_pct)
            passed = within_limit
            threshold_value = -dd_threshold
            actual_value = daily_pnl
            detail = f"24h pnl ${daily_pnl:.2f} vs floor ${-dd_threshold:.2f}"

        elif gate_name == "slippage_check":
            max_slippage = float(bot_config.get("max_slippage_pct", 0.03))
            token_id = market.yes_token_id if (market and side == "BUY_YES") else (market.no_token_id if market else "")
            orderbook = await polymarket.fetch_orderbook(token_id) if token_id else {"bids": [], "asks": []}
            spread = polymarket.compute_spread(orderbook)
            est_slippage = spread / 2
            actual_value = est_slippage
            threshold_value = max_slippage
            passed = est_slippage <= max_slippage
            detail = f"est slippage {actual_value:.4f} vs max {threshold_value:.4f}"

        check = RiskGateCheck(
            id=str(uuid.uuid4()),
            signal_id=signal.id,
            gate_name=gate_name,
            sequence=seq,
            passed=passed,
            threshold_value=float(threshold_value),
            actual_value=float(actual_value),
            detail=detail,
            checked_at=datetime.utcnow(),
        )
        db.add(check)
        checks.append(check)

        await redis_client.publish("risk:activity", {
            "ts": check.checked_at.isoformat(),
            "signal_id": signal.id,
            "gate_name": gate_name,
            "sequence": seq,
            "passed": passed,
            "threshold_value": float(threshold_value),
            "actual_value": float(actual_value),
            "detail": detail,
        })

        if not passed and gate_name != "kill_switch":
            # Non-kill-switch failures don't short-circuit remaining gates — we want full
            # visibility into every threshold for the UI grid — but the overall result is
            # still a fail (caller computes all(g.passed for g in gates)).
            pass

    await db.commit()
    for c in checks:
        await db.refresh(c)

    return checks
