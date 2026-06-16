"""
Paper trading broker: fills at mark price with simulated slippage.
Safe default — no real orders are ever placed.
"""
import uuid
from datetime import datetime
from decimal import Decimal
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.models import Trade, Position, Episode
from app.core import redis_client

log = structlog.get_logger()

SLIPPAGE_PCT = 0.0005   # 0.05% slippage simulation


def _liq_price(side: str, entry: float, leverage: int) -> float:
    maintenance_margin = 0.004   # 0.4% maintenance
    if side == "long":
        return round(entry * (1 - (1 / leverage) + maintenance_margin), 4)
    else:
        return round(entry * (1 + (1 / leverage) - maintenance_margin), 4)


async def open_position(
    db: AsyncSession,
    episode_id: str,
    market: str,
    symbol: str,
    side: str,
    leverage: int,
    mark_price: float,
    notional_usd: float,
    strategy_name: str,
    signal_id: str | None,
) -> Trade:
    slippage = mark_price * SLIPPAGE_PCT * (1 if side == "long" else -1)
    entry_price = mark_price + slippage
    qty = notional_usd / entry_price

    trade = Trade(
        id=str(uuid.uuid4()),
        episode_id=episode_id,
        market=market,
        symbol=symbol,
        side=side,
        leverage=leverage,
        entry_price=entry_price,
        qty=qty,
        notional=notional_usd,
        strategy_name=strategy_name,
        signal_id=signal_id,
        is_open=True,
        opened_at=datetime.utcnow(),
    )
    db.add(trade)

    liq = _liq_price(side, entry_price, leverage)
    position = Position(
        id=str(uuid.uuid4()),
        episode_id=episode_id,
        trade_id=trade.id,
        market=market,
        symbol=symbol,
        side=side,
        leverage=leverage,
        entry_price=entry_price,
        mark_price=mark_price,
        qty=qty,
        notional=notional_usd,
        liquidation_price=liq,
        liq_distance_pct=abs(mark_price - liq) / mark_price * 100,
        strategy_name=strategy_name,
    )
    db.add(position)
    await db.commit()

    await redis_client.publish(f"trade_update:{market}", {
        "market": market, "type": "open", "symbol": symbol,
        "side": side, "leverage": leverage, "entry_price": entry_price,
        "notional": notional_usd, "strategy": strategy_name,
    })

    log.info("position_opened", symbol=symbol, side=side, leverage=leverage,
             entry=entry_price, notional=notional_usd)
    return trade


async def close_position(
    db: AsyncSession,
    trade: Trade,
    mark_price: float,
    reason: str,
) -> float:
    slippage = mark_price * SLIPPAGE_PCT * (-1 if trade.side == "long" else 1)
    exit_price = mark_price + slippage

    if trade.side == "long":
        raw_pnl = (exit_price - trade.entry_price) * trade.qty
    else:
        raw_pnl = (trade.entry_price - exit_price) * trade.qty
    leveraged_pnl = raw_pnl * trade.leverage
    pnl_pct = leveraged_pnl / trade.notional * 100

    trade.exit_price = exit_price
    trade.pnl = round(leveraged_pnl, 4)
    trade.pnl_pct = round(pnl_pct, 2)
    trade.reason = reason
    trade.is_open = False
    trade.closed_at = datetime.utcnow()

    # Remove position
    result = await db.execute(select(Position).where(Position.trade_id == trade.id))
    pos = result.scalar_one_or_none()
    if pos:
        await db.delete(pos)

    await db.commit()

    await redis_client.publish(f"trade_update:{trade.market}", {
        "market": trade.market, "type": "close", "symbol": trade.symbol,
        "pnl": leveraged_pnl, "pnl_pct": pnl_pct, "reason": reason,
    })

    log.info("position_closed", symbol=trade.symbol, pnl=leveraged_pnl, reason=reason)
    return leveraged_pnl
