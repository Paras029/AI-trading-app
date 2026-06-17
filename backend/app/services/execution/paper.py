"""
Paper trading broker for Polymarket prediction markets: fills at the CURRENT REAL
Polymarket price with simulated slippage. Safe default — no real orders are ever placed.
"""
import uuid
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Trade, PredictionMarket, PredictionSignal
from app.core import redis_client
from app.services.market_data import polymarket
from app.services import portfolio as portfolio_service

log = structlog.get_logger()

SLIPPAGE_PCT = 0.0005   # 0.05% slippage simulation — same convention as the old broker


async def fill_order(
    db: AsyncSession,
    portfolio,
    signal: PredictionSignal,
    side: str,
    stake_usdc: float,
    kelly_fraction_used: float,
) -> Trade:
    """
    Fills at the CURRENT REAL Polymarket price (polymarket.fetch_price) — simulated fills
    against real live odds, not synthetic. shares = stake_usdc / entry_price, small
    simulated slippage. Decrements portfolio.current_balance, persists
    Trade(status='open', exec_venue='paper'), publishes 'trade_update'.
    """
    market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == signal.market_id))
    market = market_result.scalar_one_or_none()
    if market is None:
        raise ValueError(f"market {signal.market_id} not found")

    token_id = market.yes_token_id if side == "YES" else market.no_token_id
    raw_price = await polymarket.fetch_price(token_id)
    if raw_price <= 0:
        raw_price = market.current_yes_price if side == "YES" else (1 - market.current_yes_price)

    slippage = raw_price * SLIPPAGE_PCT
    entry_price = min(max(raw_price + slippage, 0.001), 0.999)
    shares = stake_usdc / entry_price

    trade = Trade(
        id=str(uuid.uuid4()),
        portfolio_id=portfolio.id,
        market_id=market.id,
        signal_id=signal.id,
        mode="paper",
        side=side,
        entry_price=entry_price,
        shares=shares,
        stake_usdc=stake_usdc,
        kelly_fraction_used=kelly_fraction_used,
        full_kelly_fraction=kelly_fraction_used,
        risk_approved=True,
        exec_venue="paper",
        status="open",
        opened_at=datetime.utcnow(),
    )
    db.add(trade)

    market.status = "traded"

    await db.commit()
    await db.refresh(trade)

    await portfolio_service.mark_trade_open(db, portfolio, stake_usdc)

    await redis_client.publish("trade_update:paper", trade_to_dict(trade))

    log.info("paper_trade_opened", market_id=market.id, side=side, entry_price=entry_price,
              shares=shares, stake_usdc=stake_usdc)
    return trade


async def settle_trade(db: AsyncSession, trade: Trade, resolved_outcome: str) -> Trade:
    """
    pnl = shares - stake_usdc if won else -stake_usdc. Updates portfolio
    balances/peak_equity. Triggers postmortem_agent.run_postmortem().
    """
    won = (trade.side == resolved_outcome)

    if won:
        payout = trade.shares  # each winning share redeems for $1
        pnl = payout - trade.stake_usdc
        trade.status = "settled_win"
    else:
        payout = 0.0
        pnl = -trade.stake_usdc
        trade.status = "settled_loss"

    trade.exit_price = 1.0 if won else 0.0
    trade.pnl = round(pnl, 4)
    trade.pnl_pct = round((pnl / trade.stake_usdc) * 100, 2) if trade.stake_usdc else 0.0
    trade.settled_at = datetime.utcnow()
    await db.commit()
    await db.refresh(trade)

    from app.db.models import Portfolio
    pf_result = await db.execute(select(Portfolio).where(Portfolio.id == trade.portfolio_id))
    pf = pf_result.scalar_one_or_none()
    if pf:
        await portfolio_service.mark_trade_closed(db, pf, pnl, payout)

    await redis_client.publish("trade_update:paper", trade_to_dict(trade))
    log.info("paper_trade_settled", trade_id=trade.id, outcome=resolved_outcome, pnl=pnl)

    try:
        from app.services.agents.postmortem_agent import run_postmortem
        await run_postmortem(db, trade)
    except Exception as e:
        log.error("postmortem_trigger_failed", trade_id=trade.id, error=str(e))

    return trade


async def close_trade_early(db: AsyncSession, trade: Trade) -> Trade:
    """
    Closes an open paper trade before market resolution, marking to the CURRENT REAL
    Polymarket price (same data source as fill_order) rather than the binary 1.0/0.0
    settlement price used by settle_trade. Triggers the same postmortem flow so lessons
    get banked for early exits too.
    """
    if trade.status != "open":
        raise ValueError(f"trade {trade.id} is not open (status={trade.status})")

    market_result = await db.execute(select(PredictionMarket).where(PredictionMarket.id == trade.market_id))
    market = market_result.scalar_one_or_none()
    if market is None:
        raise ValueError(f"market {trade.market_id} not found")

    token_id = market.yes_token_id if trade.side == "YES" else market.no_token_id
    current_price = await polymarket.fetch_price(token_id) if token_id else 0.0
    if current_price <= 0:
        current_price = market.current_yes_price if trade.side == "YES" else (1 - market.current_yes_price)

    if trade.side == "YES":
        payout = trade.shares * current_price
    else:
        payout = trade.shares * (1 - current_price)
    pnl = payout - trade.stake_usdc

    trade.exit_price = current_price
    trade.pnl = round(pnl, 4)
    trade.pnl_pct = round((pnl / trade.stake_usdc) * 100, 2) if trade.stake_usdc else 0.0
    trade.status = "closed_early"
    trade.settled_at = datetime.utcnow()
    await db.commit()
    await db.refresh(trade)

    from app.db.models import Portfolio
    pf_result = await db.execute(select(Portfolio).where(Portfolio.id == trade.portfolio_id))
    pf = pf_result.scalar_one_or_none()
    if pf:
        await portfolio_service.mark_trade_closed(db, pf, pnl, payout)

    await redis_client.publish("trade_update:paper", trade_to_dict(trade))
    log.info("paper_trade_closed_early", trade_id=trade.id, exit_price=current_price, pnl=pnl)

    try:
        from app.services.agents.postmortem_agent import run_postmortem
        await run_postmortem(db, trade)
    except Exception as e:
        log.error("postmortem_trigger_failed", trade_id=trade.id, error=str(e))

    return trade


def trade_to_dict(trade: Trade) -> dict:
    return {
        "id": trade.id,
        "portfolio_id": trade.portfolio_id,
        "market_id": trade.market_id,
        "signal_id": trade.signal_id,
        "mode": trade.mode,
        "side": trade.side,
        "entry_price": trade.entry_price,
        "shares": trade.shares,
        "stake_usdc": trade.stake_usdc,
        "kelly_fraction_used": trade.kelly_fraction_used,
        "full_kelly_fraction": trade.full_kelly_fraction,
        "risk_approved": trade.risk_approved,
        "exec_venue": trade.exec_venue,
        "exec_order_id": trade.exec_order_id,
        "exec_tx_hash": trade.exec_tx_hash,
        "status": trade.status,
        "exit_price": trade.exit_price,
        "pnl": trade.pnl,
        "pnl_pct": trade.pnl_pct,
        "opened_at": trade.opened_at.isoformat() if trade.opened_at else None,
        "settled_at": trade.settled_at.isoformat() if trade.settled_at else None,
    }
