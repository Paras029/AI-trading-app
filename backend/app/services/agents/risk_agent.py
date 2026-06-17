"""
Risk Agent — Stage 4 of the pipeline. Computes Kelly sizing, runs the 9-gate risk
evaluation, and (if all gates pass + live-armed check clears) dispatches to paper or
live execution.
"""
import structlog
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Trade, PredictionMarket, PredictionSignal
from app.core import redis_client
from app.services import portfolio as portfolio_service
from app.services.risk import gates, kelly
from app.services.execution import paper

log = structlog.get_logger()


async def run_risk_check(db: AsyncSession, signal: PredictionSignal) -> Trade | None:
    """
    1. portfolio = get_or_create_portfolio(db, mode=bot_config['prediction_trading_mode'])
    2. full_kelly + proposed_stake via risk/kelly.py
    3. gates.evaluate_gates(db, signal, portfolio, bot_config)
    4. if not all passed: publish rejection, return None
    5. live_armed check: mode=='live' and not bot_config['live_armed'] -> hard fail
       ('live_not_armed') even if all 9 gates passed.
    6. dispatch to execution.paper.fill_order() or execution.polymarket_live.place_order().
    7. Publishes APPROVED/REJECTED to redis_client.publish('risk:decision', {...}).
    """
    bot_config = await redis_client.get_bot_config()
    mode = bot_config.get("prediction_trading_mode", "paper")

    pf = await portfolio_service.get_or_create_portfolio(db, mode=mode)

    side = signal.action  # BUY_YES | BUY_NO
    kelly_side = side
    full_kelly = kelly.kelly_fraction_full(signal.final_probability, signal.market_price, kelly_side)
    kelly_multiplier = float(bot_config.get("kelly_multiplier", 0.25))
    single_cap = float(bot_config.get("single_position_cap_usd", 100.0))
    proposed_stake = kelly.kelly_stake(full_kelly, kelly_multiplier, pf.total_equity, single_cap)

    checks = await gates.evaluate_gates(db, signal, pf, bot_config)
    all_passed = all(c.passed for c in checks)

    market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == signal.market_id))
    market = market_result.scalar_one_or_none()

    if not all_passed:
        market.status = "rejected" if market else market
        if market:
            await db.commit()
        failed_gate = next((c.gate_name for c in checks if not c.passed), "unknown")
        await redis_client.publish("risk:decision", {
            "id": signal.id,
            "signal_id": signal.id,
            "approved": False,
            "trade_id": None,
            "kelly_fraction_full": round(full_kelly, 4),
            "kelly_fraction_applied": 0.0,
            "stake_usdc": 0.0,
            "checked_at": datetime.utcnow().isoformat(),
            "reason": f"failed_gate:{failed_gate}",
        })
        log.info("risk_check_rejected", signal_id=signal.id, failed_gate=failed_gate)
        return None

    trade_side = "YES" if side == "BUY_YES" else "NO"

    if mode == "live" and not bot_config.get("live_armed", False):
        await redis_client.publish("risk:decision", {
            "id": signal.id,
            "signal_id": signal.id,
            "approved": False,
            "trade_id": None,
            "kelly_fraction_full": round(full_kelly, 4),
            "kelly_fraction_applied": 0.0,
            "stake_usdc": 0.0,
            "checked_at": datetime.utcnow().isoformat(),
            "reason": "live_not_armed",
        })
        log.warning("risk_check_blocked_live_not_armed", signal_id=signal.id)
        if market:
            market.status = "rejected"
            await db.commit()
        return None

    try:
        if mode == "live":
            from app.services.execution import polymarket_live
            trade = await polymarket_live.place_order(db, pf, signal, trade_side, proposed_stake, full_kelly * kelly_multiplier)
        else:
            trade = await paper.fill_order(db, pf, signal, trade_side, proposed_stake, full_kelly * kelly_multiplier)
    except Exception as e:
        log.error("risk_check_execution_failed", signal_id=signal.id, error=str(e))
        await redis_client.publish("risk:decision", {
            "id": signal.id,
            "signal_id": signal.id,
            "approved": False,
            "trade_id": None,
            "kelly_fraction_full": round(full_kelly, 4),
            "kelly_fraction_applied": 0.0,
            "stake_usdc": 0.0,
            "checked_at": datetime.utcnow().isoformat(),
            "reason": f"execution_failed:{str(e)[:120]}",
        })
        if market:
            market.status = "rejected"
            await db.commit()
        return None

    if market:
        market.status = "traded"
        await db.commit()

    await redis_client.publish("risk:decision", {
        "id": trade.id,
        "signal_id": signal.id,
        "approved": True,
        "trade_id": trade.id,
        "kelly_fraction_full": round(full_kelly, 4),
        "kelly_fraction_applied": round(full_kelly * kelly_multiplier, 4),
        "stake_usdc": round(proposed_stake, 2),
        "checked_at": datetime.utcnow().isoformat(),
    })
    log.info("risk_check_approved", signal_id=signal.id, trade_id=trade.id, mode=mode)
    return trade
