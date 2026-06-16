"""
Risk manager: Kelly position sizing, stop-loss/take-profit checks,
leverage limits, liquidation monitoring, and daily loss limit.
"""
import structlog
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import Episode, Position, Trade

log = structlog.get_logger()

# Default risk params — updated per generation by episode_reviewer
DEFAULT_KELLY = 0.25
DEFAULT_MAX_LEVERAGE = 6
STOP_LOSS_PCT = 0.05       # 5% stop-loss on notional
TAKE_PROFIT_PCT = 0.15     # 15% take-profit on notional
LIQ_DISTANCE_WARN_PCT = 5  # warn when liq is within 5%


def kelly_position_size(
    equity: float,
    kelly_fraction: float,
    leverage: int,
    confidence: float,
) -> float:
    """Returns notional USD to allocate to this trade."""
    base = equity * kelly_fraction * min(confidence, 1.0)
    max_notional = equity * 0.5   # never risk more than 50% of equity on one trade
    return min(base, max_notional)


async def check_signal(
    db: AsyncSession,
    episode: Episode,
    signal: dict,
    kelly_fraction: float = DEFAULT_KELLY,
    max_leverage: int = DEFAULT_MAX_LEVERAGE,
) -> dict | None:
    """
    Returns a trade decision dict or None if vetoed.
    """
    action = signal.get("action")
    if action == "HOLD":
        return None

    confidence = signal.get("confidence", 0.5)
    if confidence < 0.55:
        log.debug("signal_vetoed_low_confidence", confidence=confidence)
        return None

    # Check existing open positions
    result = await db.execute(
        select(Position).where(Position.episode_id == episode.id)
    )
    open_positions = result.scalars().all()

    if len(open_positions) >= 3:
        log.debug("signal_vetoed_too_many_positions", count=len(open_positions))
        return None

    notional = kelly_position_size(episode.current_equity, kelly_fraction, max_leverage, confidence)
    if notional < 5.0:
        log.debug("signal_vetoed_insufficient_equity", equity=episode.current_equity)
        return None

    leverage = min(max_leverage, int(max_leverage * confidence))
    leverage = max(1, leverage)

    return {
        "side": "long" if action == "BUY" else "short",
        "leverage": leverage,
        "notional": round(notional, 2),
    }


async def monitor_stop_loss_take_profit(
    db: AsyncSession,
    episode: Episode,
    current_prices: dict[str, float],
) -> list[tuple[Trade, str]]:
    """Returns list of (trade, reason) pairs that should be closed."""
    result = await db.execute(
        select(Trade).where(Trade.episode_id == episode.id, Trade.is_open == True)
    )
    trades = result.scalars().all()

    to_close = []
    for trade in trades:
        price = current_prices.get(trade.symbol)
        if price is None:
            continue

        if trade.side == "long":
            raw_pnl_pct = (price - trade.entry_price) / trade.entry_price
        else:
            raw_pnl_pct = (trade.entry_price - price) / trade.entry_price

        lev_pnl_pct = raw_pnl_pct * trade.leverage

        if lev_pnl_pct <= -STOP_LOSS_PCT:
            to_close.append((trade, "stop-loss"))
        elif lev_pnl_pct >= TAKE_PROFIT_PCT:
            to_close.append((trade, "take-profit"))

    return to_close


async def check_daily_loss_limit(
    db: AsyncSession,
    episode: Episode,
    limit_pct: float = 0.10,
) -> bool:
    """Returns True if the bot lost more than limit_pct of current equity in the last 24h."""
    since = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(func.sum(Trade.pnl)).where(
            Trade.episode_id == episode.id,
            Trade.closed_at >= since,
            Trade.is_open == False,
        )
    )
    daily_pnl = float(result.scalar() or 0.0)
    threshold = episode.current_equity * limit_pct
    if daily_pnl < -threshold:
        log.warning("daily_loss_limit_hit", daily_pnl=daily_pnl, threshold=-threshold)
        return True
    return False
