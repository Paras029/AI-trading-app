"""
Extracts situational tags from a prediction-market trade context, then scores knowledge
entries / past post-mortems against those tags so the most relevant history surfaces in
each research brief / post-mortem prompt.

score_entry()'s formula is reused byte-for-byte from the old technical-indicator bot — it
has zero domain-specific logic. extract_context_tags() is fully rewritten with prediction-
market vocabulary (category, edge_bucket, sentiment_gap_bucket, role_agreement,
failure_category).
"""
from __future__ import annotations


def _bucket_edge(edge_pct: float) -> str:
    edge_pct = abs(edge_pct)
    if edge_pct >= 0.20:
        return "edge_huge"
    if edge_pct >= 0.10:
        return "edge_large"
    if edge_pct >= 0.05:
        return "edge_medium"
    return "edge_small"


def _bucket_gap(gap_pct: float) -> str:
    gap_pct = abs(gap_pct)
    if gap_pct >= 0.20:
        return "sentiment_gap_extreme"
    if gap_pct >= 0.10:
        return "sentiment_gap_large"
    if gap_pct >= 0.05:
        return "sentiment_gap_medium"
    return "sentiment_gap_small"


def extract_context_tags(
    category: str = "",
    edge_pct: float | None = None,
    gap_pct: float | None = None,
    role_agreement_pct: float | None = None,
    failure_category: str | None = None,
    source_agreement_pct: float | None = None,
    used_xgboost: bool | None = None,
    action: str | None = None,
) -> list[str]:
    """Build a flat tag list describing the situational context of a prediction-market
    trade or research pass, for scoring against KnowledgeEntry / PostMortem rows."""
    tags: list[str] = []

    if category:
        tags.append(f"category_{category.lower().replace(' ', '_')}")

    if edge_pct is not None:
        tags.append(_bucket_edge(edge_pct))
        tags.append("edge_positive" if edge_pct > 0 else "edge_negative")

    if gap_pct is not None:
        tags.append(_bucket_gap(gap_pct))

    if role_agreement_pct is not None:
        if role_agreement_pct >= 0.80:
            tags.append("role_agreement_high")
        elif role_agreement_pct >= 0.50:
            tags.append("role_agreement_moderate")
        else:
            tags.append("role_agreement_low")

    if source_agreement_pct is not None:
        if source_agreement_pct >= 0.80:
            tags.append("source_agreement_high")
        elif source_agreement_pct >= 0.50:
            tags.append("source_agreement_moderate")
        else:
            tags.append("source_agreement_low")

    if failure_category:
        tags.append(f"failure_{failure_category}")

    if used_xgboost is not None:
        tags.append("xgboost_blended" if used_xgboost else "ensemble_only")

    if action:
        tags.append(f"action_{action.lower()}")

    return list(dict.fromkeys(tags))  # deduplicate, preserve order


def score_entry(entry, context_tags: list[str]) -> float:
    """Score a KnowledgeEntry (or PostMortem-like object exposing .tags/.importance/
    .times_referenced) against current context tags. Reused byte-for-byte from the
    pre-rewrite technical-indicator bot — zero domain-specific logic."""
    entry_tags = list(entry.tags or [])
    if not entry_tags:
        overlap_fraction = 0.0
    else:
        matched = len(set(entry_tags) & set(context_tags))
        overlap_fraction = matched / len(entry_tags)

    importance = getattr(entry, "importance", 5)
    times_ref = getattr(entry, "times_referenced", 0)

    return (importance * 0.4) + (overlap_fraction * 10 * 0.6) + min(times_ref * 0.5, 2.0)
