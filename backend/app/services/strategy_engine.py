"""
Strategy engine: seeds default strategies, evaluates stats gates,
and promotes/retires strategies after each episode.
"""
import uuid
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Strategy, Trade

log = structlog.get_logger()

# Statistical gates to earn "active" status
MIN_EXP_R = 0.0
MIN_PROFIT_FACTOR = 1.0
MIN_SHARPE = 0.4
MIN_TRADES = 10

DEFAULT_STRATEGIES = [
    {
        "name": "15m Breakout (Donchian)",
        "description": "Long/short when price breaks above/below the 20-period Donchian channel on the 15m chart.",
    },
    {
        "name": "Time-Series Momentum",
        "description": "Long when 1m EMA50 > EMA200 and upward; short when below. Momentum continuation.",
    },
    {
        "name": "RSI-2 Mean Reversion",
        "description": "Buy when RSI(2) < 10 (extreme oversold), sell when RSI(2) > 90 (extreme overbought). Connors method.",
    },
    {
        "name": "Momentum + Trend Filter",
        "description": "Long breakouts only when ADX > 25 (trending). Avoids choppy markets.",
    },
]


async def seed_strategies(db: AsyncSession, market: str) -> None:
    for s in DEFAULT_STRATEGIES:
        result = await db.execute(
            select(Strategy).where(Strategy.name == s["name"], Strategy.market == market)
        )
        if not result.scalar_one_or_none():
            db.add(Strategy(
                id=str(uuid.uuid4()),
                name=s["name"],
                market=market,
                status="candidate",
                description=s["description"],
            ))
    await db.commit()


async def get_active_strategy_names(db: AsyncSession, market: str) -> list[str]:
    result = await db.execute(
        select(Strategy).where(Strategy.market == market, Strategy.status == "active")
    )
    return [s.name for s in result.scalars()]


async def update_strategy_stats(db: AsyncSession, market: str) -> None:
    """Recompute Exp R, PF, Sharpe for each strategy from closed trades."""
    strategies = (await db.execute(select(Strategy).where(Strategy.market == market))).scalars().all()
    for strategy in strategies:
        result = await db.execute(
            select(Trade).where(
                Trade.market == market,
                Trade.strategy_name == strategy.name,
                Trade.is_open == False,
                Trade.pnl != None,
            )
        )
        trades = result.scalars().all()
        if not trades:
            continue

        pnls = [t.pnl for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        n = len(pnls)

        win_rate = len(wins) / n if n else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0
        exp_r = win_rate * avg_win - (1 - win_rate) * avg_loss
        profit_factor = (sum(wins) / abs(sum(losses))) if losses else float("inf")

        import statistics
        if n >= 2:
            mean_pnl = sum(pnls) / n
            std_pnl = statistics.stdev(pnls)
            sharpe = (mean_pnl / std_pnl * (n ** 0.5)) if std_pnl > 0 else 0
        else:
            sharpe = 0.0

        strategy.exp_r = round(exp_r, 4)
        strategy.profit_factor = round(profit_factor, 4)
        strategy.sharpe = round(sharpe, 4)
        strategy.win_rate = round(win_rate, 4)
        strategy.num_trades = n
        strategy.updated_at = datetime.utcnow()

        if (n >= MIN_TRADES and exp_r > MIN_EXP_R
                and profit_factor > MIN_PROFIT_FACTOR
                and sharpe > MIN_SHARPE
                and strategy.status == "candidate"):
            strategy.status = "active"
            log.info("strategy_promoted", name=strategy.name, market=market)

    await db.commit()
