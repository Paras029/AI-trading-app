"""
Portfolio service — replaces episode_manager.py's role as the equity ledger.
One Portfolio row per trading mode (paper|live), created lazily on first use.
"""
import uuid
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Portfolio
from app.config import settings

log = structlog.get_logger()


async def get_or_create_portfolio(db: AsyncSession, mode: str = "paper") -> Portfolio:
    result = await db.execute(select(Portfolio).where(Portfolio.mode == mode))
    portfolio = result.scalar_one_or_none()
    if portfolio:
        return portfolio

    starting_balance = settings.portfolio_starting_balance
    portfolio = Portfolio(
        id=str(uuid.uuid4()),
        mode=mode,
        starting_balance=starting_balance,
        current_balance=starting_balance,
        total_equity=starting_balance,
        peak_equity=starting_balance,
        realized_pnl_today=0.0,
        realized_pnl_alltime=0.0,
        num_trades_total=0,
        num_trades_open=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    log.info("portfolio_created", mode=mode, starting_balance=starting_balance)
    return portfolio


async def update_balance(db: AsyncSession, portfolio: Portfolio, delta: float) -> Portfolio:
    """Apply a balance delta (positive or negative) and recompute total_equity/peak_equity."""
    portfolio.current_balance = round(portfolio.current_balance + delta, 4)
    portfolio.total_equity = round(portfolio.total_equity + delta, 4)
    if portfolio.total_equity > portfolio.peak_equity:
        portfolio.peak_equity = portfolio.total_equity
    portfolio.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


async def mark_trade_open(db: AsyncSession, portfolio: Portfolio, stake_usdc: float) -> Portfolio:
    """Decrement current_balance by the staked amount and bump open/total trade counters."""
    portfolio.current_balance = round(portfolio.current_balance - stake_usdc, 4)
    portfolio.num_trades_open += 1
    portfolio.num_trades_total += 1
    portfolio.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


async def mark_trade_closed(db: AsyncSession, portfolio: Portfolio, pnl: float, payout: float) -> Portfolio:
    """
    On settlement: credit the payout (stake back + pnl if won, $0 if lost — the stake was
    already debited at open time), update realized P&L and peak_equity, decrement open count.
    """
    portfolio.current_balance = round(portfolio.current_balance + payout, 4)
    portfolio.total_equity = round(portfolio.current_balance, 4)
    portfolio.realized_pnl_today = round(portfolio.realized_pnl_today + pnl, 4)
    portfolio.realized_pnl_alltime = round(portfolio.realized_pnl_alltime + pnl, 4)
    if portfolio.total_equity > portfolio.peak_equity:
        portfolio.peak_equity = portfolio.total_equity
    portfolio.num_trades_open = max(0, portfolio.num_trades_open - 1)
    portfolio.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(portfolio)
    return portfolio
