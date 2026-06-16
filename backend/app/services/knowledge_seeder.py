"""
Seeds the knowledge base with proven trading frameworks on first run.
Claude consults these before every signal + episode review.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import KnowledgeEntry

SEED_KNOWLEDGE = [
    {
        "category": "risk",
        "market": "all",
        "title": "Kelly Criterion",
        "content": "Never risk more than the Kelly fraction of your bankroll on a single trade. Full Kelly is theoretically optimal but practically dangerous — use half-Kelly (0.25) to reduce variance while maintaining growth. Formula: f = (bp - q) / b where b=odds, p=win probability, q=loss probability.",
        "importance": 10,
    },
    {
        "category": "risk",
        "market": "all",
        "title": "Van Tharp Position Sizing",
        "content": "Risk a fixed percentage of equity per trade (1-2% for conservative; up to 5% for aggressive). Position size = (Account Risk %) / (Stop Loss %). This ensures no single trade can destroy the account.",
        "importance": 10,
    },
    {
        "category": "regime",
        "market": "all",
        "title": "Market Regime Filter",
        "content": "Trend-following strategies work best when ADX > 25 and price is trending. Mean-reversion works in ranging markets (ADX < 20, price oscillating between Bollinger bands). Never use trend strategies in chop — reduces win rate dramatically.",
        "importance": 9,
    },
    {
        "category": "risk",
        "market": "crypto",
        "title": "Liquidation Price Awareness",
        "content": "With leveraged futures: always know your liquidation price before entering. Keep at least 10% buffer between current price and liq price. If liq distance < 5%, reduce position immediately. A liquidation wipes the entire position.",
        "importance": 10,
    },
    {
        "category": "strategy",
        "market": "crypto",
        "title": "Donchian Breakout Rules",
        "content": "Long: price breaks above 20-period high on 15m chart. Short: breaks below 20-period low. Only enter in trending regime (ADX > 25). Set stop at the opposite channel boundary. Target 1.5x the channel width.",
        "importance": 8,
    },
    {
        "category": "strategy",
        "market": "all",
        "title": "RSI Extremes Mean Reversion",
        "content": "RSI(14) below 25 = oversold, consider long. RSI(14) above 75 = overbought, consider short. Only in ranging markets. Do NOT fade RSI extremes in strong trends — RSI can stay extreme for extended periods in trending conditions.",
        "importance": 7,
    },
    {
        "category": "risk",
        "market": "all",
        "title": "Stop Loss Discipline",
        "content": "Always set stop loss before entering. Never move stop loss against the position. A 5% stop on notional with 6x leverage = 30% account risk — be conservative. After a blow-up episode: halve leverage until 10 profitable trades restore confidence.",
        "importance": 10,
    },
    {
        "category": "regime",
        "market": "crypto",
        "title": "Fear & Greed as Contrarian Signal",
        "content": "Extreme Fear (< 25): markets oversold, historically good for longs but exercise caution in downtrends. Extreme Greed (> 75): markets overextended, reduce long exposure, consider shorts. Do not trade against the primary trend based on sentiment alone.",
        "importance": 7,
    },
    {
        "category": "risk",
        "market": "all",
        "title": "Consecutive Losses Rule",
        "content": "After 3 consecutive losses: pause for at least 1 hour. After 5 consecutive losses: stop for the day. This prevents revenge trading and emotional decision-making, which amplifies losses in drawdowns.",
        "importance": 9,
    },
    {
        "category": "strategy",
        "market": "us_stocks",
        "title": "US Market Hours Awareness",
        "content": "US stocks trade 9:30am-4:00pm EST. First 30 minutes and last 30 minutes are most volatile. Avoid trading 30 minutes before major economic releases (Fed meetings, NFP, CPI). Gap risk is highest at open.",
        "importance": 8,
    },
    {
        "category": "strategy",
        "market": "india_stocks",
        "title": "India Market Session Rules",
        "content": "NSE/BSE trade 9:15am-3:30pm IST. Pre-market 9:00-9:15am. Avoid the first 15 minutes as price discovery settles. Nifty options have high liquidity; individual stocks can have wide spreads. F&O expiry on last Thursday of each month creates volatility.",
        "importance": 8,
    },
    {
        "category": "risk",
        "market": "all",
        "title": "Correlation Risk",
        "content": "Do not hold multiple highly correlated positions simultaneously. BTC and ETH are ~0.85 correlated. If you hold both, your effective exposure is much larger than it appears. Treat correlated pairs as a single larger position for risk sizing.",
        "importance": 8,
    },
]


async def seed_knowledge_base(db: AsyncSession) -> None:
    count_result = await db.execute(select(func.count()).select_from(KnowledgeEntry).where(KnowledgeEntry.source == "system"))
    count = count_result.scalar()
    if count and count >= len(SEED_KNOWLEDGE):
        return   # already seeded

    for entry in SEED_KNOWLEDGE:
        existing = await db.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.title == entry["title"])
        )
        if not existing.scalar_one_or_none():
            db.add(KnowledgeEntry(
                id=str(uuid.uuid4()),
                source="system",
                **entry,
            ))
    await db.commit()
