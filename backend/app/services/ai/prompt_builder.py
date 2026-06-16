"""
Assembles prompts for the signal generator and episode reviewer.
"""
from app.core import redis_client
from app.config import PROMPT_DEPTH_CONFIG


SIGNAL_SYSTEM_PROMPT = """You are Apex, an AI trading bot operating in paper simulation mode on real live prices.
You study technical indicators, market regime, news sentiment, and the knowledge base to generate disciplined trade signals.

Rules you must follow:
1. Never risk more than Kelly-adjusted position size.
2. In Risk Off regime: reduce leverage, prefer short side or HOLD.
3. Only act on active strategies. Candidate strategies get reduced sizing.
4. If RSI > 75 (overbought) and regime is trending, prefer SHORT or HOLD.
5. If RSI < 25 (oversold) and regime is trending, prefer LONG or HOLD.
6. When in doubt, HOLD. Capital preservation is the primary goal.
7. After a blow-up lesson: increase stop-loss discipline immediately.

Return ONLY valid JSON matching this schema:
{"action": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "reasoning": "...", "risk_note": "..."}"""


async def build_signal_prompt(
    symbol: str,
    market: str,
    recent_candles: list[dict],
    indicators: dict,
    active_strategies: list[str],
    recent_signals: list[dict],
    knowledge_snippets: list[str],
    depth: str = "standard",
    historical_snippets: list[str] | None = None,
    upcoming_events: list[dict] | None = None,
) -> str:
    dc = PROMPT_DEPTH_CONFIG.get(depth, PROMPT_DEPTH_CONFIG["standard"])
    n_candles = dc["candles"]
    n_headlines = dc["headlines"]
    n_knowledge = dc["knowledge"]

    world = await redis_client.get_json("world:context") or {}

    candle_lines = "\n".join(
        f"  O:{c.get('o',0):.2f} H:{c.get('h',0):.2f} L:{c.get('l',0):.2f} C:{c.get('c',0):.2f} V:{c.get('v',0):.0f}"
        for c in recent_candles[-n_candles:]
    )

    fng = world.get("crypto_fng" if market == "crypto" else "stock_fng", {})
    regime = world.get("regime", "Unknown")
    headlines = world.get("headlines", {}).get(
        "crypto" if market == "crypto" else ("india" if market == "india_stocks" else "us"), []
    )
    macro = world.get("macro", {})

    signal_history = "\n".join(
        f"  {s.get('action','')} conf:{s.get('confidence',0):.2f} — {s.get('reasoning','')[:60]}"
        for s in recent_signals[-2:]
    ) or "  None"

    knowledge = "\n".join(f"  • {k}" for k in knowledge_snippets[:n_knowledge]) or "  None."

    ind = indicators or {}
    bb = ind.get("bollinger", {})
    macd = ind.get("macd", {})

    # Build optional UPCOMING section
    upcoming_section = ""
    if upcoming_events:
        imminent = [e for e in upcoming_events if e.get("hours_until", 999) < 48]
        if imminent:
            event_parts = " | ".join(
                f"{e['title']} in {e['hours_until']}h" for e in imminent[:3]
            )
            upcoming_section = f"\nUPCOMING ⚠: {event_parts} → reduce position sizes\n"

    # Build optional HISTORICAL PARALLELS section
    historical_section = ""
    if historical_snippets:
        lines = "\n".join(f"  {h}" for h in historical_snippets)
        historical_section = f"\nHISTORICAL PARALLELS:\n{lines}\n"

    macro_ctx = ""
    if macro:
        parts = []
        if "VIX" in macro:   parts.append(f"VIX:{macro['VIX']:.1f}")
        if "US10Y" in macro:  parts.append(f"US10Y:{macro['US10Y']:.2f}%")
        if "DXY" in macro:    parts.append(f"DXY:{macro['DXY']:.1f}")
        if parts:
            macro_ctx = " " + " ".join(parts)

    return f"""Symbol: {symbol} | Market: {market} | Price: {ind.get('current_price', 'N/A')}

CANDLES (last {n_candles}):
{candle_lines}

INDICATORS:
  RSI:{ind.get('rsi')} MACD:{macd.get('macd')} Hist:{macd.get('histogram')}
  BB upper:{bb.get('upper')} lower:{bb.get('lower')}
  EMA20:{ind.get('ema_20')} EMA50:{ind.get('ema_50')} ADX:{ind.get('adx')}

CONTEXT: Regime:{regime} F&G:{fng.get('value')}({fng.get('label')}) Funding:{world.get('funding_rate',0):.4f}{macro_ctx}
HEADLINES: {' | '.join(headlines[:n_headlines]) or 'None'}{upcoming_section}{historical_section}
RULES: {knowledge}
STRATEGIES: {', '.join(active_strategies) or 'default'}
PRIOR SIGNALS: {signal_history}

Respond JSON only: {{"action":"BUY|SELL|HOLD","confidence":0.0-1.0,"reasoning":"...","risk_note":"..."}}"""


REVIEW_SYSTEM_PROMPT = """You are Apex's post-episode analyst. After each episode ends (goal hit or blow-up), you:
1. Write lessons learned — plain English, tagged by market regime, importance 1-10 (blow-ups score higher).
2. Write the Generation summary — what changes for the next generation (Kelly fraction, max leverage, strategy promotions/retirements).

Return JSON with two keys:
{
  "lessons": [{"title": "...", "body": "...", "regime": "...", "importance": 1-10}],
  "generation": {
    "summary": "...",
    "kelly_fraction": 0.0-1.0,
    "max_leverage": int,
    "promote_strategies": ["..."],
    "retire_strategies": ["..."]
  }
}"""


def build_review_prompt(episode: dict, trades: list[dict], existing_lessons: list[str]) -> str:
    trade_summary = "\n".join(
        f"  {t.get('opened_at','')} {t.get('side','').upper()} {t.get('symbol','')} x{t.get('leverage',1)} → {t.get('reason','')}: PnL ${t.get('pnl',0):.2f} ({t.get('pnl_pct',0):.1f}%)"
        for t in trades[:50]
    ) or "  No trades."

    return f"""Episode #{episode.get('generation', '?')} just ended.
Outcome: {episode.get('outcome', 'unknown').upper()}
Start equity: ${episode.get('start_equity', 100):.2f}
Final equity: ${episode.get('current_equity', 0):.2f}
Peak equity: ${episode.get('peak_equity', 0):.2f}
Goal: ${episode.get('goal_equity', 500):.2f}
Total trades: {episode.get('num_trades', 0)}
Market: {episode.get('market', 'crypto')}

TRADE HISTORY:
{trade_summary}

PRIOR LESSONS (do not repeat verbatim):
{chr(10).join('• ' + l for l in existing_lessons[:10]) or 'None'}

Analyse what happened. What should the bot do differently next generation?
Respond with JSON only."""
