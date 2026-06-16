"""
Calls Claude to generate a BUY/SELL/HOLD signal with structured JSON output.
"""
import json
import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
from app.core import redis_client
from app.services.ai.prompt_builder import SIGNAL_SYSTEM_PROMPT, build_signal_prompt

log = structlog.get_logger()

_client: AsyncAnthropic | None = None

SIGNAL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
        "risk_note": {"type": "string"},
    },
    "required": ["action", "confidence", "reasoning", "risk_note"],
    "additionalProperties": False,
}


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_signal(
    symbol: str,
    market: str,
    episode_id: str,
    recent_candles: list[dict],
    indicators: dict,
    active_strategies: list[str],
    recent_signals: list[dict],
    knowledge_snippets: list[str],
) -> dict | None:
    lock_key = f"signal_lock:{market}:{symbol}"
    if not await redis_client.set_lock(lock_key, settings.signal_cooldown_seconds):
        log.debug("signal_cooldown_active", symbol=symbol)
        return None

    user_prompt = await build_signal_prompt(
        symbol, market, recent_candles, indicators,
        active_strategies, recent_signals, knowledge_snippets,
    )

    try:
        response = await get_client().messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": SIGNAL_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        signal_data = json.loads(raw)
        log.info("signal_generated", symbol=symbol, action=signal_data.get("action"), confidence=signal_data.get("confidence"))
        return signal_data
    except Exception as e:
        log.error("signal_generation_failed", symbol=symbol, error=str(e))
        raise
