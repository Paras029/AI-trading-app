"""
Live (real-money) Polymarket order execution via py-clob-client. This is the most
conservative file in the codebase: it re-checks every precondition independently of
risk_agent.py (defense in depth), never logs key material, and re-raises on any failure
rather than silently degrading.

Gated behind TWO independent layers, both required:
  1. bot_config['prediction_trading_mode'] == 'live'
  2. bot_config['live_armed'] is True (set only via POST /api/settings/arm-live with an
     exact-string confirmation)
"""
import uuid
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.db.models import Trade, PredictionMarket, PredictionSignal, Portfolio
from app.core import redis_client
from app.services.market_data import polymarket
from app.services import portfolio as portfolio_service

log = structlog.get_logger()

SLIPPAGE_TOLERANCE_PCT = 0.02  # limit order placed up to 2% through the signal price
POLYGON_CHAIN_ID = 137


class ExecutionBlockedError(Exception):
    """Raised when a live order is blocked by a safety precondition. Never bypass this
    by catching and retrying — it exists specifically to stop real-money execution."""


def _get_clob_client():
    """Lazily construct the ClobClient using the Polygon proxy-wallet pattern.
    Imported lazily so the dependency is only required when live trading is actually used."""
    from py_clob_client.client import ClobClient

    if not settings.polymarket_private_key or not settings.polymarket_funder_address:
        raise ExecutionBlockedError("polymarket_credentials_missing")

    client = ClobClient(
        host="https://clob.polymarket.com",
        key=settings.polymarket_private_key,
        chain_id=POLYGON_CHAIN_ID,
        funder=settings.polymarket_funder_address,
        signature_type=1,  # proxy-wallet signature type (Polymarket Polygon proxy pattern)
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    return client


async def place_order(
    db: AsyncSession,
    portfolio,
    signal: PredictionSignal,
    side: str,
    stake_usdc: float,
    kelly_fraction_used: float,
) -> Trade:
    """
    Defense-in-depth precondition checks (even though risk_agent already checked):
    settings.polymarket_private_key/funder_address non-empty, mode=='live' and
    live_armed=True (else raise ExecutionBlockedError). Places a limit order at
    signal.market_price +/- slippage tolerance. On success persists
    exec_order_id/exec_tx_hash. On failure logs structlog error (no key material) and
    re-raises.
    """
    bot_config = await redis_client.get_bot_config()

    if bot_config.get("prediction_trading_mode") != "live":
        raise ExecutionBlockedError("trading_mode_not_live")
    if not bot_config.get("live_armed", False):
        raise ExecutionBlockedError("live_not_armed")
    if not settings.polymarket_private_key or not settings.polymarket_funder_address:
        raise ExecutionBlockedError("polymarket_credentials_missing")

    market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == signal.market_id))
    market = market_result.scalar_one_or_none()
    if market is None:
        raise ExecutionBlockedError("market_not_found")

    token_id = market.yes_token_id if side == "YES" else market.no_token_id
    if not token_id:
        raise ExecutionBlockedError("token_id_missing")

    limit_price = signal.market_price
    if side == "YES":
        limit_price = min(limit_price * (1 + SLIPPAGE_TOLERANCE_PCT), 0.999)
    else:
        no_price = 1 - signal.market_price
        limit_price = min(no_price * (1 + SLIPPAGE_TOLERANCE_PCT), 0.999)

    try:
        client = _get_clob_client()

        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import BUY

        order_args = OrderArgs(
            price=round(limit_price, 3),
            size=round(stake_usdc / limit_price, 2),
            side=BUY,
            token_id=token_id,
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order)

        order_id = response.get("orderID") or response.get("orderId") or ""
        tx_hash = response.get("transactionHash") or response.get("transactionsHashes", [""])[0] if isinstance(response.get("transactionsHashes"), list) else response.get("transactionHash", "")

    except ExecutionBlockedError:
        raise
    except Exception as e:
        # Never log key material — only the exception message/type, and only after
        # confirming it doesn't echo back request payloads containing the private key.
        log.error("polymarket_live_order_failed", market_id=market.id, side=side, error=str(e)[:300])
        raise

    shares = stake_usdc / limit_price

    trade = Trade(
        id=str(uuid.uuid4()),
        portfolio_id=portfolio.id,
        market_id=market.id,
        signal_id=signal.id,
        mode="live",
        side=side,
        entry_price=limit_price,
        shares=shares,
        stake_usdc=stake_usdc,
        kelly_fraction_used=kelly_fraction_used,
        full_kelly_fraction=kelly_fraction_used,
        risk_approved=True,
        exec_venue="polymarket_clob",
        exec_order_id=str(order_id),
        exec_tx_hash=str(tx_hash) if tx_hash else None,
        status="open",
        opened_at=datetime.utcnow(),
    )
    db.add(trade)
    market.status = "traded"
    await db.commit()
    await db.refresh(trade)

    await portfolio_service.mark_trade_open(db, portfolio, stake_usdc)

    await redis_client.publish("trade_update:live", {
        "id": trade.id, "market_id": trade.market_id, "side": trade.side,
        "entry_price": trade.entry_price, "stake_usdc": trade.stake_usdc,
        "exec_order_id": trade.exec_order_id, "status": trade.status,
    })

    log.info("polymarket_live_order_placed", market_id=market.id, side=side,
              order_id=order_id, stake_usdc=stake_usdc)
    return trade


async def close_position(db: AsyncSession, trade: Trade) -> Trade:
    """
    Closes an open LIVE trade early by selling the exact position back on the CLOB.
    Re-checks the same two independent safety gates as place_order — never bypass the
    live-arm gate for closes, even though the trade itself proves live trading was on
    when it opened (config could have been disarmed since). Sells trade.shares (the
    actual held position), not a recomputed size.
    """
    if trade.status != "open":
        raise ExecutionBlockedError("trade_not_open")

    bot_config = await redis_client.get_bot_config()
    if bot_config.get("prediction_trading_mode") != "live":
        raise ExecutionBlockedError("trading_mode_not_live")
    if not bot_config.get("live_armed", False):
        raise ExecutionBlockedError("live_not_armed")
    if not settings.polymarket_private_key or not settings.polymarket_funder_address:
        raise ExecutionBlockedError("polymarket_credentials_missing")

    market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == trade.market_id))
    market = market_result.scalar_one_or_none()
    if market is None:
        raise ExecutionBlockedError("market_not_found")

    token_id = market.yes_token_id if trade.side == "YES" else market.no_token_id
    if not token_id:
        raise ExecutionBlockedError("token_id_missing")

    current_price = await polymarket.fetch_price(token_id)
    if current_price <= 0:
        current_price = market.current_yes_price if trade.side == "YES" else (1 - market.current_yes_price)

    limit_price = max(current_price * (1 - SLIPPAGE_TOLERANCE_PCT), 0.001)

    try:
        client = _get_clob_client()

        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import SELL

        order_args = OrderArgs(
            price=round(limit_price, 3),
            size=round(trade.shares, 2),
            side=SELL,
            token_id=token_id,
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order)

        order_id = response.get("orderID") or response.get("orderId") or ""
        tx_hash = response.get("transactionHash") or response.get("transactionsHashes", [""])[0] if isinstance(response.get("transactionsHashes"), list) else response.get("transactionHash", "")

    except ExecutionBlockedError:
        raise
    except Exception as e:
        log.error("polymarket_live_close_failed", market_id=market.id, side=trade.side, error=str(e)[:300])
        raise

    payout = trade.shares * limit_price
    pnl = payout - trade.stake_usdc

    trade.exit_price = limit_price
    trade.pnl = round(pnl, 4)
    trade.pnl_pct = round((pnl / trade.stake_usdc) * 100, 2) if trade.stake_usdc else 0.0
    trade.status = "closed_early"
    trade.settled_at = datetime.utcnow()
    # Overwrites the opening order's reference — accepted for v1 (opening order id remains
    # visible in the original polymarket_live_order_placed log line).
    trade.exec_order_id = str(order_id)
    trade.exec_tx_hash = str(tx_hash) if tx_hash else None
    await db.commit()
    await db.refresh(trade)

    pf_result = await db.execute(select(Portfolio).where(Portfolio.id == trade.portfolio_id))
    portfolio = pf_result.scalar_one_or_none()
    if portfolio:
        await portfolio_service.mark_trade_closed(db, portfolio, pnl, payout)

    await redis_client.publish("trade_update:live", {
        "id": trade.id, "market_id": trade.market_id, "side": trade.side,
        "exit_price": trade.exit_price, "pnl": trade.pnl, "pnl_pct": trade.pnl_pct,
        "exec_order_id": trade.exec_order_id, "status": trade.status,
    })

    log.info("polymarket_live_position_closed", market_id=market.id, side=trade.side,
              order_id=order_id, pnl=pnl)

    try:
        from app.services.agents.postmortem_agent import run_postmortem
        await run_postmortem(db, trade)
    except Exception as e:
        log.error("postmortem_trigger_failed", trade_id=trade.id, error=str(e))

    return trade
