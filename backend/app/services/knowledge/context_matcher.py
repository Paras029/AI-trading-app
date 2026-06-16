"""
Extracts situational tags from live market data, then scores knowledge entries
against those tags so the most relevant history surfaces in each signal prompt.
"""
from __future__ import annotations


def extract_context_tags(
    market: str,
    indicators: dict,
    world: dict,
    upcoming_events: list[dict] | None = None,
) -> list[str]:
    tags: list[str] = [market]
    macro = world.get("macro", {})
    upcoming_events = upcoming_events or []

    # ── Volatility (VIX) ──────────────────────────────────────────────────────
    vix = macro.get("VIX", 15)
    if vix > 40:
        tags += ["vix_extreme", "crisis_volatility", "risk_off"]
    elif vix > 30:
        tags += ["vix_high", "risk_off"]
    elif vix < 15:
        tags.append("vix_low")

    # ── Interest rates (US 10Y) ───────────────────────────────────────────────
    us10y = macro.get("US10Y", 4.0)
    if us10y > 5.0:
        tags += ["ten_year_high", "rate_hike_cycle"]
    elif us10y > 4.5:
        tags.append("ten_year_high")
    elif us10y < 3.5:
        tags += ["ten_year_low", "rate_cut_cycle"]

    # ── Dollar strength (DXY) ─────────────────────────────────────────────────
    dxy = macro.get("DXY", 100)
    if dxy > 105:
        tags.append("dxy_high")
    elif dxy > 102:
        tags.append("dxy_rising")
    elif dxy < 95:
        tags.append("dxy_low")

    # ── Commodities ───────────────────────────────────────────────────────────
    oil = macro.get("OIL", 75)
    if oil > 100:
        tags += ["oil_spike", "oil_high"]
    elif oil > 85:
        tags.append("oil_high")

    gold = macro.get("GOLD", 1900)
    if gold > 2500:
        tags += ["gold_spike", "gold_high"]
    elif gold > 2200:
        tags.append("gold_high")

    # ── Market regime ─────────────────────────────────────────────────────────
    regime = world.get("regime", "Neutral")
    if regime == "Risk Off":
        tags.append("risk_off")
    elif regime == "Risk On":
        tags.append("risk_on")

    # ── Sentiment / Fear & Greed ──────────────────────────────────────────────
    fng_key = "crypto_fng" if market == "crypto" else "stock_fng"
    fng = world.get(fng_key, {}).get("value", 50)
    if fng < 20:
        tags.append("extreme_fear")
    elif fng < 40:
        tags.append("fear")
    elif fng > 80:
        tags.append("extreme_greed")
    elif fng > 60:
        tags.append("greed")

    # ── Crypto funding rate ───────────────────────────────────────────────────
    funding = world.get("funding_rate", 0)
    if funding > 0.07:
        tags += ["funding_extreme", "crowded_long"]
    elif funding > 0.03:
        tags.append("funding_high")
    elif funding < -0.05:
        tags += ["funding_negative", "crowded_short"]
    elif funding < -0.02:
        tags.append("funding_negative")

    # ── Per-symbol technicals ─────────────────────────────────────────────────
    rsi = indicators.get("rsi", 50)
    if rsi is not None:
        if rsi < 25:
            tags.append("oversold")
        elif rsi > 75:
            tags.append("overbought")

    # ── Economic calendar events ──────────────────────────────────────────────
    for evt in upcoming_events:
        title = evt.get("title", "").upper()
        hours = evt.get("hours_until", 999)
        if hours < 48:
            tags.append("high_impact_event")
        if "FOMC" in title or "RATE DECISION" in title or "FEDERAL RESERVE" in title:
            tags += ["fomc_week", "fed_event"]
        if "CPI" in title or "CONSUMER PRICE" in title:
            tags.append("cpi_event")
        if "NON-FARM" in title or "NFP" in title or "NONFARM" in title:
            tags.append("nfp_event")
        if "GDP" in title:
            tags.append("gdp_event")

    # ── Headline keyword scan ──────────────────────────────────────────────────
    all_headlines = " ".join(
        h.get("title", "") if isinstance(h, dict) else h
        for hl in world.get("headlines", {}).values()
        for h in hl
    ).lower()
    if any(w in all_headlines for w in ["war", "conflict", "sanctions", "invasion", "military", "missile"]):
        tags.append("geopolitical_risk")
    if any(w in all_headlines for w in ["bankrupt", "collapse", "hack", "insolvent", "fraud", "contagion"]):
        tags.append("contagion_risk")
    if any(w in all_headlines for w in ["halving", "etf approval", "etf rejected", "sec crypto"]):
        tags.append("crypto_regulatory")

    return list(dict.fromkeys(tags))  # deduplicate, preserve order


def score_entry(entry, context_tags: list[str]) -> float:
    """Score a KnowledgeEntry against current context tags."""
    entry_tags = list(entry.tags or [])
    if not entry_tags:
        overlap_fraction = 0.0
    else:
        matched = len(set(entry_tags) & set(context_tags))
        overlap_fraction = matched / len(entry_tags)

    importance = getattr(entry, "importance", 5)
    times_ref = getattr(entry, "times_referenced", 0)

    return (importance * 0.4) + (overlap_fraction * 10 * 0.6) + min(times_ref * 0.5, 2.0)
