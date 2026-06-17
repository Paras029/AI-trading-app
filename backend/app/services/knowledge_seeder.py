"""
Seeds the knowledge base with a small set of domain-general risk-discipline frameworks on
first run. The Research Agent and Post-Mortem Agent both consult this table (scored via
knowledge/context_matcher.py::score_entry()) before writing their analysis.

Replaces the old 149-entry technical-indicator-bot seed list (Kelly/position-sizing rules
ported across since they're market-mechanics-agnostic; VIX/sector-rotation/crash-history
entries dropped — they don't apply to binary prediction markets). The knowledge base is
intentionally small at seed time: it grows organically as the Post-Mortem Agent mirrors
importance>=7 lessons into it after real trades settle.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db.models import KnowledgeEntry

SEED_KNOWLEDGE = [
    {
        "category": "risk_management",
        "market": "all",
        "title": "Kelly Criterion for Binary Markets",
        "content": (
            "For a binary YES/NO market, full Kelly fraction = edge / odds, where edge is "
            "your model probability minus the market-implied probability and odds reflect the "
            "payout per dollar staked at the current price. Full Kelly is theoretically growth-"
            "optimal but has high variance — this bot always applies a kelly_multiplier (default "
            "0.25, i.e. quarter-Kelly) to the full-Kelly fraction before sizing a position. Never "
            "increase the multiplier after a string of wins; that is exactly when overconfidence "
            "compounds the next loss."
        ),
        "importance": 10,
        "tags": ["risk_management"],
    },
    {
        "category": "risk_management",
        "market": "all",
        "title": "Kill-Switch Discipline",
        "content": (
            "The kill_switch gate is evaluated first and short-circuits all 8 remaining risk "
            "gates to failed/skipped when the bot is paused. Never bypass or weaken this gate to "
            "let a single high-conviction trade through — a kill-switch that has exceptions is "
            "not a kill-switch. If the bot is paused, the correct action is to fix whatever "
            "triggered the pause, not to find a path around it."
        ),
        "importance": 10,
        "tags": ["risk_management"],
    },
    {
        "category": "risk_management",
        "market": "all",
        "title": "Edge Decays as Markets Approach Resolution",
        "content": (
            "A prediction market's price converges toward the true outcome probability as the "
            "resolution date approaches and more information becomes public — this is why edge "
            "is most exploitable early, while sentiment/news lag the market, and why scanner_max_"
            "expiry_days filters out markets too far from resolution to act on with current "
            "information. A large edge in a market expiring in days is far more suspicious "
            "(possible stale data or a one-sided information asymmetry you don't have) than the "
            "same edge in a market with weeks left."
        ),
        "importance": 8,
        "tags": ["risk_management", "edge_large", "edge_huge"],
    },
    {
        "category": "risk_management",
        "market": "all",
        "title": "Drawdown Recovery Math Is Asymmetric",
        "content": (
            "A 10% loss requires an 11% gain to recover. A 20% loss requires 25%. A 50% loss "
            "requires 100%. This asymmetry is why max_drawdown_pct and daily_loss_limit_pct exist "
            "as hard gates rather than soft suggestions — capital preservation compounds, and a "
            "single oversized loss can erase many small wins' worth of edge."
        ),
        "importance": 9,
        "tags": ["risk_management", "max_drawdown"],
    },
    {
        "category": "risk_management",
        "market": "all",
        "title": "Consensus Among Forecaster Roles Is Not Proof of Correctness",
        "content": (
            "When all 5 forecast-ensemble roles (primary, news analyst, bull/bear advocates, risk "
            "contrarian) agree closely, it can mean the thesis is genuinely strong — or it can "
            "mean every role is anchoring on the same narrative/training-data bias and the "
            "Risk Contrarian role failed to do its job of finding the counter-case. Low "
            "role_agreement_pct combined with a still-positive edge deserves more scrutiny, not "
            "less, before sizing up."
        ),
        "importance": 7,
        "tags": ["risk_management", "role_agreement_high", "role_agreement_low"],
    },
    {
        "category": "risk_management",
        "market": "all",
        "title": "Source Agreement Does Not Equal Source Quality",
        "content": (
            "High source_agreement_pct from the Research Agent's sentiment aggregation means "
            "most gathered Reddit/news items lean the same direction — it says nothing about "
            "whether those sources are independent or all echoing the same original report. "
            "Treat a unanimous but thin (few-source) signal with more caution than a divided but "
            "well-sourced one; the sentiment weighting already down-weights anonymous/low-score "
            "sources, but volume of agreement is still not the same as evidentiary strength."
        ),
        "importance": 7,
        "tags": ["risk_management", "source_agreement_high"],
    },
    {
        "category": "risk_management",
        "market": "all",
        "title": "Cold-Start Caution Before the XGBoost Blend Activates",
        "content": (
            "Until xgboost_min_samples settled trades exist, the Prediction Agent's final "
            "probability is the raw LLM-ensemble average with no historical calibration check. "
            "This is expected and fine — it is simply a higher-uncertainty regime. Position "
            "sizing via the Kelly multiplier already accounts for this since Kelly sizing is "
            "directly proportional to edge confidence; do not manually compensate by raising the "
            "Kelly multiplier just because the blend hasn't activated yet."
        ),
        "importance": 6,
        "tags": ["risk_management", "ensemble_only"],
    },
    {
        "category": "risk_management",
        "market": "all",
        "title": "Live Trading Requires Two Independent Confirmations",
        "content": (
            "Switching from paper to live execution requires both prediction_trading_mode=='live' "
            "and a separate live_armed flag set only via an explicit, exact-phrase confirmation "
            "endpoint. Both the Risk Agent and the live execution layer re-check both conditions "
            "independently (defense in depth) — if either check is ever weakened to 'trust the "
            "caller already checked', a single bug anywhere upstream could route real money "
            "through an unconfirmed path. Never trade live-sized lessons learned in paper mode "
            "without re-validating them against live execution's slippage and fee reality."
        ),
        "importance": 9,
        "tags": ["risk_management"],
    },
]


async def seed_knowledge_base(db: AsyncSession) -> None:
    count_result = await db.execute(
        select(func.count()).select_from(KnowledgeEntry).where(KnowledgeEntry.source == "system")
    )
    count = count_result.scalar()
    if count and count >= len(SEED_KNOWLEDGE):
        return  # already seeded

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
