"""
Manages episode lifecycle: open, monitor, close, trigger evolution.
"""
import uuid
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Episode, Generation, Lesson, Trade, Strategy, KnowledgeEntry
from app.db.models.episode import EpisodeOutcome
from app.services.ai.episode_reviewer import review_episode
from app.core import redis_client
from app.config import settings

log = structlog.get_logger()


async def get_or_create_active_episode(db: AsyncSession, market: str) -> Episode:
    result = await db.execute(
        select(Episode).where(
            Episode.market == market,
            Episode.outcome == EpisodeOutcome.running,
        ).order_by(Episode.start_at.desc()).limit(1)
    )
    episode = result.scalar_one_or_none()
    if episode:
        return episode
    return await open_episode(db, market)


async def open_episode(db: AsyncSession, market: str, generation: int = 1,
                        start_equity: float | None = None,
                        goal_multiplier: float | None = None) -> Episode:
    start = start_equity or settings.episode_start_equity
    multiplier = goal_multiplier or settings.episode_goal_multiplier
    episode = Episode(
        id=str(uuid.uuid4()),
        market=market,
        generation=generation,
        start_equity=start,
        goal_equity=round(start * multiplier, 2),
        current_equity=start,
        peak_equity=start,
        outcome=EpisodeOutcome.running,
        start_at=datetime.utcnow(),
    )
    db.add(episode)
    await db.commit()
    log.info("episode_opened", market=market, generation=generation, start=start, goal=episode.goal_equity)
    return episode


async def check_episode_completion(db: AsyncSession, episode: Episode) -> bool:
    if episode.current_equity >= episode.goal_equity:
        return await end_episode(db, episode, EpisodeOutcome.goal)
    blowup_floor = episode.start_equity * 0.1   # lose 90% = blowup
    if episode.current_equity <= blowup_floor:
        return await end_episode(db, episode, EpisodeOutcome.blowup)
    return False


async def end_episode(db: AsyncSession, episode: Episode, outcome: EpisodeOutcome) -> bool:
    episode.outcome = outcome
    episode.end_at = datetime.utcnow()
    await db.commit()
    log.info("episode_ended", market=episode.market, outcome=outcome.value,
             equity=episode.current_equity, generation=episode.generation)

    await redis_client.publish(f"episode_update:{episode.market}", {
        "market": episode.market,
        "episode_id": episode.id,
        "outcome": outcome.value,
        "generation": episode.generation,
        "final_equity": episode.current_equity,
    })

    # Trigger AI evolution
    await evolve(db, episode)
    return True


async def update_equity(db: AsyncSession, episode: Episode, pnl_delta: float) -> None:
    episode.current_equity = round(episode.current_equity + pnl_delta, 4)
    if episode.current_equity > episode.peak_equity:
        episode.peak_equity = episode.current_equity
    episode.num_trades += 1
    await db.commit()


async def evolve(db: AsyncSession, episode: Episode) -> None:
    """Run post-episode AI review and open next generation."""
    result = await db.execute(
        select(Trade).where(Trade.episode_id == episode.id).order_by(Trade.opened_at)
    )
    trades = result.scalars().all()
    trade_dicts = [
        {
            "symbol": t.symbol, "side": t.side, "leverage": t.leverage,
            "entry_price": t.entry_price, "exit_price": t.exit_price,
            "pnl": t.pnl, "pnl_pct": t.pnl_pct, "reason": t.reason,
            "strategy_name": t.strategy_name,
            "opened_at": t.opened_at.isoformat() if t.opened_at else "",
        }
        for t in trades
    ]

    # Fetch existing lessons as plain strings for context
    lesson_result = await db.execute(
        select(Lesson).where(Lesson.market == episode.market).order_by(Lesson.importance.desc()).limit(20)
    )
    existing_lessons = [f"{l.title}: {l.body[:100]}" for l in lesson_result.scalars()]

    episode_dict = {
        "generation": episode.generation,
        "market": episode.market,
        "outcome": episode.outcome.value if hasattr(episode.outcome, "value") else episode.outcome,
        "start_equity": episode.start_equity,
        "current_equity": episode.current_equity,
        "peak_equity": episode.peak_equity,
        "goal_equity": episode.goal_equity,
        "num_trades": episode.num_trades,
    }

    try:
        review = await review_episode(episode_dict, trade_dicts, existing_lessons)
    except Exception as e:
        log.error("evolution_review_failed", error=str(e))
        review = {"lessons": [], "generation": {
            "summary": f"Auto-generated after {episode.outcome}",
            "kelly_fraction": 0.25, "max_leverage": 6,
            "promote_strategies": [], "retire_strategies": [],
        }}

    gen_data = review.get("generation", {})
    lessons_data = review.get("lessons", [])

    # Persist generation
    gen = Generation(
        id=str(uuid.uuid4()),
        market=episode.market,
        number=episode.generation + 1,
        after_episode_id=episode.id,
        summary_text=gen_data.get("summary", ""),
        kelly_fraction=gen_data.get("kelly_fraction", 0.25),
        max_leverage=gen_data.get("max_leverage", 6),
        lessons_count=len(lessons_data),
        promoted_strategies=",".join(gen_data.get("promote_strategies", [])),
        retired_strategies=",".join(gen_data.get("retire_strategies", [])),
    )
    db.add(gen)

    # Persist lessons
    for l in lessons_data:
        lesson = Lesson(
            id=str(uuid.uuid4()),
            episode_id=episode.id,
            generation_id=gen.id,
            market=episode.market,
            title=l.get("title", ""),
            body=l.get("body", ""),
            market_regime=l.get("regime", "unknown"),
            importance=l.get("importance", 5),
        )
        db.add(lesson)

        # High-importance lessons also go into the knowledge base
        if l.get("importance", 0) >= 7:
            kb = KnowledgeEntry(
                id=str(uuid.uuid4()),
                category="lesson",
                market=episode.market,
                title=l.get("title", ""),
                content=l.get("body", ""),
                source="episode_review",
                importance=l.get("importance", 5),
            )
            db.add(kb)

    # Update strategy statuses
    for name in gen_data.get("promote_strategies", []):
        r = await db.execute(select(Strategy).where(Strategy.name == name, Strategy.market == episode.market))
        s = r.scalar_one_or_none()
        if s:
            s.status = "active"
    for name in gen_data.get("retire_strategies", []):
        r = await db.execute(select(Strategy).where(Strategy.name == name, Strategy.market == episode.market))
        s = r.scalar_one_or_none()
        if s:
            s.status = "retired"

    await db.commit()

    # Open next episode with evolved params
    await open_episode(
        db, episode.market,
        generation=episode.generation + 1,
        start_equity=settings.episode_start_equity,
    )

    log.info("evolution_complete", market=episode.market, new_gen=episode.generation + 1,
             lessons=len(lessons_data))
