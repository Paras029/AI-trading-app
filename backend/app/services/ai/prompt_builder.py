"""
Assembles prompts for the signal generator and episode reviewer.
"""
from app.core import redis_client


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
) -> str:
    world = await redis_client.get_json("world:context") or {}

    candle_lines = "\n".join(
        f"  {c.get('t','')} O:{c.get('o',0):.2f} H:{c.get('h',0):.2f} L:{c.get('l',0):.2f} C:{c.get('c',0):.2f} V:{c.get('v',0):.0f}"
        for c in recent_candles[-10:]
    )

    fng = world.get("crypto_fng" if market == "crypto" else "stock_fng", {})
    regime = world.get("regime", "Unknown")
    headlines = world.get("headlines", {}).get(
        "crypto" if market == "crypto" else ("india" if market == "india_stocks" else "us"), []
    )

    signal_history = "\n".join(
        f"  {s.get('created_at','')} → {s.get('action','')} (conf:{s.get('confidence',0):.2f}): {s.get('reasoning','')[:80]}"
        for s in recent_signals[-2:]
    ) or "  None"

    knowledge = "\n".join(f"  • {k}" for k in knowledge_snippets[:5]) or "  No specific knowledge loaded."

    ind = indicators or {}
    bb = ind.get("bollinger", {})
    macd = ind.get("macd", {})

    return f"""Symbol: {symbol} | Market: {market} | Current Price: {ind.get('current_price', 'N/A')}

RECENT CANDLES (last 10):
{candle_lines}

TECHNICAL INDICATORS:
  RSI(14): {ind.get('rsi')}
  MACD: {macd.get('macd')} | Signal: {macd.get('signal')} | Histogram: {macd.get('histogram')}
  Bollinger: Upper={bb.get('upper')} Mid={bb.get('middle')} Lower={bb.get('lower')}
  EMA20: {ind.get('ema_20')} | EMA50: {ind.get('ema_50')}
  ADX(14): {ind.get('adx')}

WORLD CONTEXT:
  Regime: {regime}
  Fear & Greed: {fng.get('value')} ({fng.get('label')})
  Funding Rate: {world.get('funding_rate', 0):.4f}
  Macro: {world.get('macro', {})}

RECENT HEADLINES:
{chr(10).join('  • ' + h for h in headlines[:5]) or '  None'}

ACTIVE STRATEGIES: {', '.join(active_strategies) or 'None — use default momentum logic'}

RECENT SIGNALS:
{signal_history}

KNOWLEDGE BASE (relevant rules):
{knowledge}

Based on all of the above, generate your trade signal. Respond with JSON only."""


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
