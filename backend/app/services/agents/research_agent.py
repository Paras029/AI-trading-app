"""
Research Agent — Stage 2 of the pipeline. Gathers Reddit + News RSS sources for a
'scanned' market, tags each source's sentiment, aggregates a narrative probability,
and persists a ResearchBrief. Publishes incremental reasoning_log steps to
redis_client.publish('research:activity', {...}) AS EACH STEP HAPPENS, driving a
live typed-log UI (not a single final blob).
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import ResearchBrief, PredictionMarket, KnowledgeEntry
from app.core import redis_client
from app.services.sentiment import reddit, news_rss
from app.services.ai import providers
from app.services.ai.prompt_builder import RESEARCH_SYSTEM_PROMPT, build_research_prompt
from app.services.knowledge import context_matcher

log = structlog.get_logger()

SENTIMENT_WEIGHTS = {
    "official": 3.0,
    "major_news": 2.0,
    "verified_account": 1.5,
    "general_social": 1.0,
    "anonymous": 0.5,
}

_BULLISH_WORDS = {
    "win", "wins", "winning", "victory", "surge", "rally", "approve", "approved",
    "confirmed", "yes", "likely", "favored", "lead", "leading", "ahead", "pass", "passed",
}
_BEARISH_WORDS = {
    "lose", "loses", "losing", "defeat", "collapse", "crash", "reject", "rejected",
    "denied", "no", "unlikely", "trail", "trailing", "behind", "fail", "failed",
}


def _source_type_for(item: dict) -> str:
    """Classify a raw source item into a SENTIMENT_WEIGHTS bucket."""
    if item.get("source") == "news_rss":
        publisher = (item.get("publisher") or "").lower()
        major = {"reuters", "associated press", "ap", "bloomberg", "bbc", "cnn", "the new york times", "the wall street journal"}
        if any(m in publisher for m in major):
            return "major_news"
        return "official" if "gov" in publisher else "major_news"
    # reddit
    score = item.get("score", 0) or 0
    if score >= 500:
        return "verified_account"
    if score >= 50:
        return "general_social"
    return "anonymous"


def _recency_decay(published_at: str | None, created_utc: float | None) -> float:
    """Exponential-ish recency decay: full weight at <1 day old, decaying to ~0.2 at 14 days."""
    now = datetime.now(timezone.utc)
    ts = None
    if created_utc:
        try:
            ts = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
        except Exception:
            ts = None
    elif published_at:
        try:
            ts = datetime.strptime(published_at, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except Exception:
            ts = None
    if ts is None:
        return 0.6  # unknown age — moderate weight
    age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
    if age_days <= 1:
        return 1.0
    if age_days >= 14:
        return 0.2
    return max(0.2, 1.0 - (age_days / 14.0) * 0.8)


def _keyword_sentiment(text: str) -> str:
    text_lower = text.lower()
    bull_hits = sum(1 for w in _BULLISH_WORDS if w in text_lower)
    bear_hits = sum(1 for w in _BEARISH_WORDS if w in text_lower)
    if bull_hits > bear_hits:
        return "bullish"
    if bear_hits > bull_hits:
        return "bearish"
    return "neutral"


async def _tag_sentiment_batch(items: list[dict], question: str) -> list[str]:
    """Tag each item's sentiment via one batched cheap LLM call, falling back to a
    keyword heuristic if no AI key is configured.

    Note: providers.call_role() is shaped around {probability, reasoning} for the
    forecast ensemble, which doesn't fit a batched per-item sentiment classification
    schema. Rather than force that mismatch, we call the provider HTTP functions
    directly here and parse a {"sentiments": [...]} response; any failure (no key,
    parse error, network error) falls back to the keyword heuristic so research never
    blocks on this step."""
    if not items:
        return []

    if not providers.has_key_for_provider("anthropic") and not providers.has_key_for_provider("google"):
        return [_keyword_sentiment(i.get("title", "")) for i in items]

    titles_block = "\n".join(f"{idx}. {i.get('title', '')[:200]}" for idx, i in enumerate(items))
    system = (
        "You classify news/social post headlines as bullish, bearish, or neutral with respect "
        "to whether they suggest the YES outcome of a prediction market question is more or less "
        "likely. Return ONLY valid JSON: {\"sentiments\": [\"bullish\"|\"bearish\"|\"neutral\", ...]} "
        "with exactly one entry per numbered headline, in order."
    )
    user = f"MARKET QUESTION: {question}\n\nHEADLINES:\n{titles_block}"

    try:
        if providers.has_key_for_provider("anthropic"):
            raw, usage = await providers.call_anthropic("claude-haiku-4-5-20251001", system, user, 400)
            model_used = "claude-haiku-4-5-20251001"
        else:
            raw, usage = await providers.call_gemini("gemini-2.0-flash", system, user, 400)
            model_used = "gemini-2.0-flash"

        from app.services.cost_tracker import track_usage
        await track_usage(model_used, "sentiment_tagger", usage, market="prediction")

        parsed = json.loads(providers._clean_json(raw))
        sentiments = parsed.get("sentiments", [])
        if len(sentiments) == len(items):
            valid = {"bullish", "bearish", "neutral"}
            return [s if s in valid else "neutral" for s in sentiments]
    except Exception as e:
        log.warning("sentiment_batch_failed", error=str(e))

    return [_keyword_sentiment(i.get("title", "")) for i in items]


async def research_market(db: AsyncSession, market: PredictionMarket) -> ResearchBrief:
    reasoning_log: list[dict] = []

    async def _log_step(step: str, message: str) -> None:
        entry = {"ts": datetime.utcnow().isoformat(), "step": step, "message": message}
        reasoning_log.append(entry)
        await redis_client.publish("research:activity", {
            "ts": entry["ts"],
            "market_id": market.id,
            "step": step,
            "message": message,
        })

    await _log_step("start", f"Researching: {market.question[:120]}")

    # ── 1. Gather sources ────────────────────────────────────────────────────
    await _log_step("gathering", "Fetching Reddit posts and news headlines...")
    query = market.question[:200]
    reddit_posts, news_items = await asyncio.gather(
        reddit.fetch_subreddit_posts(query, limit=15),
        news_rss.fetch_news_for_market(query, limit=10),
        return_exceptions=True,
    )
    reddit_posts = reddit_posts if isinstance(reddit_posts, list) else []
    news_items = news_items if isinstance(news_items, list) else []
    all_items = reddit_posts + news_items
    await _log_step("gathered", f"Found {len(reddit_posts)} Reddit posts, {len(news_items)} news items.")

    # ── 2. Sentiment tagging ─────────────────────────────────────────────────
    await _log_step("tagging", "Tagging sentiment for each source...")
    sentiments = await _tag_sentiment_batch(all_items, market.question)
    for item, sentiment in zip(all_items, sentiments):
        item["sentiment"] = sentiment

    # ── 3. Weight by source-type x recency decay ─────────────────────────────
    await _log_step("weighting", "Weighting sources by type and recency...")
    sources: list[dict] = []
    bullish_weight = bearish_weight = neutral_weight = 0.0
    for item in all_items:
        source_type = _source_type_for(item)
        base_weight = SENTIMENT_WEIGHTS.get(source_type, 1.0)
        decay = _recency_decay(item.get("published_at"), item.get("created_utc"))
        weight = base_weight * decay
        sentiment = item.get("sentiment", "neutral")

        if sentiment == "bullish":
            bullish_weight += weight
        elif sentiment == "bearish":
            bearish_weight += weight
        else:
            neutral_weight += weight

        sources.append({
            "source": item.get("source", "unknown"),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "sentiment": sentiment,
            "weight": round(weight, 3),
            "published_at": item.get("published_at") or "",
        })

    total_weight = bullish_weight + bearish_weight + neutral_weight
    if total_weight > 0:
        bullish_pct = bullish_weight / total_weight
        bearish_pct = bearish_weight / total_weight
        neutral_pct = neutral_weight / total_weight
    else:
        bullish_pct = bearish_pct = neutral_pct = 1.0 / 3.0

    # Source agreement: how dominant the majority sentiment is vs. an even 3-way split
    max_pct = max(bullish_pct, bearish_pct, neutral_pct)
    source_agreement_pct = max(0.0, (max_pct - (1 / 3)) / (1 - (1 / 3)))

    # ── 4. Narrative probability + gap ───────────────────────────────────────
    denom = bullish_weight + bearish_weight
    narrative_probability = (bullish_weight / denom) if denom > 0 else 0.5
    market_implied_probability = market.current_yes_price
    gap_pct = narrative_probability - market_implied_probability

    await _log_step(
        "aggregated",
        f"Narrative probability {narrative_probability:.2f} vs market {market_implied_probability:.2f} "
        f"(gap {gap_pct:+.2f}). Source agreement {source_agreement_pct:.0%}.",
    )

    # ── 5. AI brief ───────────────────────────────────────────────────────────
    await _log_step("writing_brief", "Synthesizing research brief...")
    brief_text = ""
    if providers.has_key_for_provider("anthropic") or providers.has_key_for_provider("google"):
        provider = "anthropic" if providers.has_key_for_provider("anthropic") else "google"
        role_config = {
            "role": "research_brief",
            "provider": provider,
            "model": "claude-haiku-4-5-20251001" if provider == "anthropic" else "gemini-2.0-flash",
            "max_tokens": 400,
        }
        prompt = build_research_prompt(
            {"question": market.question, "category": market.category, "current_yes_price": market.current_yes_price},
            sources,
        )
        try:
            # build_research_prompt + RESEARCH_SYSTEM_PROMPT return {"brief_text": "..."},
            # which doesn't match call_role's {probability, reasoning} schema, so we call
            # the provider directly here and parse the brief_text key ourselves.
            if provider == "anthropic":
                raw, usage = await providers.call_anthropic(role_config["model"], RESEARCH_SYSTEM_PROMPT, prompt, 400)
            else:
                raw, usage = await providers.call_gemini(role_config["model"], RESEARCH_SYSTEM_PROMPT, prompt, 400)
            from app.services.cost_tracker import track_usage
            await track_usage(role_config["model"], "research_brief", usage, market="prediction")
            parsed = json.loads(providers._clean_json(raw))
            brief_text = parsed.get("brief_text", "")
        except Exception as e:
            log.warning("research_brief_ai_failed", error=str(e))
            brief_text = (
                f"AI brief unavailable ({e}). {len(sources)} sources gathered: "
                f"{bullish_pct:.0%} bullish, {bearish_pct:.0%} bearish, {neutral_pct:.0%} neutral."
            )
    else:
        brief_text = (
            f"No AI key configured — heuristic summary only. {len(sources)} sources: "
            f"{bullish_pct:.0%} bullish, {bearish_pct:.0%} bearish, {neutral_pct:.0%} neutral."
        )

    await _log_step("brief_done", brief_text[:200])

    # ── 6. Similar past knowledge ────────────────────────────────────────────
    await _log_step("retrieving_knowledge", "Looking up similar historical context...")
    context_tags = context_matcher.extract_context_tags(
        category=market.category,
        gap_pct=gap_pct,
        source_agreement_pct=source_agreement_pct,
    )
    kb_result = await db.execute(select(KnowledgeEntry))
    entries = list(kb_result.scalars())
    scored = sorted(
        ((context_matcher.score_entry(e, context_tags), e) for e in entries),
        key=lambda x: x[0], reverse=True,
    )
    top3 = [e for _, e in scored[:3]]
    if top3:
        await _log_step("knowledge_found", f"Top match: {top3[0].title}")

    # ── 7. Persist ────────────────────────────────────────────────────────────
    brief = ResearchBrief(
        id=str(uuid.uuid4()),
        market_id=market.id,
        created_at=datetime.utcnow(),
        bullish_pct=round(bullish_pct, 4),
        bearish_pct=round(bearish_pct, 4),
        neutral_pct=round(neutral_pct, 4),
        source_agreement_pct=round(source_agreement_pct, 4),
        narrative_probability=round(narrative_probability, 4),
        market_implied_probability=round(market_implied_probability, 4),
        gap_pct=round(gap_pct, 4),
        brief_text=brief_text,
        reasoning_log=reasoning_log,
        sources=sources,
    )
    db.add(brief)

    market.status = "researched"
    await db.commit()
    await db.refresh(brief)

    await _log_step("done", "Research complete.")
    return brief
