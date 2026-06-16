"""
Calls Claude or Gemini to generate a BUY/SELL/HOLD signal with structured JSON output.
Model and prompt depth are read from Redis runtime config at call time.
"""
import asyncio
import json
import httpx
import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings, PROMPT_DEPTH_CONFIG, AVAILABLE_SIGNAL_MODELS
from app.core import redis_client
from app.services.ai.prompt_builder import SIGNAL_SYSTEM_PROMPT, build_signal_prompt
from app.services.cost_tracker import track_usage

log = structlog.get_logger()

_anthropic_client: AsyncAnthropic | None = None

# Build provider lookup from config
_MODEL_PROVIDER: dict[str, str] = {
    m["id"]: m.get("provider", "anthropic")
    for m in AVAILABLE_SIGNAL_MODELS
}

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_API_BASE_V1 = "https://generativelanguage.googleapis.com/v1/models"

# Models that need the stable v1 endpoint
_GEMINI_V1_MODELS = {"gemini-2.5-flash", "gemini-2.0-flash"}

# ── Gemini rate limiter ────────────────────────────────────────────────────────
# Free tier: 15 RPM. We schedule calls at 4.5s intervals (≈13 RPM) to stay safe.
# Callers atomically claim a time slot, then wait outside the lock.
_gemini_slot_lock = asyncio.Lock()
_gemini_next_slot: float = 0.0
_GEMINI_SLOT_INTERVAL = 4.5  # seconds between calls


async def _claim_gemini_slot() -> float:
    """Return the monotonic time at which this caller may fire its request."""
    global _gemini_next_slot
    loop = asyncio.get_event_loop()
    async with _gemini_slot_lock:
        now = loop.time()
        slot = max(now, _gemini_next_slot)
        _gemini_next_slot = slot + _GEMINI_SLOT_INTERVAL
        return slot


def get_anthropic_client() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=30))
async def _call_anthropic(model: str, max_tokens: int, user_prompt: str) -> tuple[str, object]:
    response = await get_anthropic_client().messages.create(
        model=model,
        max_tokens=max_tokens,
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
    return raw, response.usage


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=10, max=60))
async def _do_gemini_http(url: str, payload: dict, api_key: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, params={"key": api_key})
        if not resp.is_success:
            log.warning("gemini_http_error", status=resp.status_code,
                        body=resp.text[:300], model=url.split("/")[-1].split(":")[0])
        resp.raise_for_status()
        return resp.json()


async def _call_gemini(model: str, max_tokens: int, user_prompt: str) -> tuple[str, dict]:
    if not settings.google_api_key:
        raise ValueError("GOOGLE_API_KEY is not configured. Add it to your .env file.")

    # Wait for our rate-limited slot
    slot = await _claim_gemini_slot()
    wait = slot - asyncio.get_event_loop().time()
    if wait > 0:
        await asyncio.sleep(wait)

    base = GEMINI_API_BASE_V1 if model in _GEMINI_V1_MODELS else GEMINI_API_BASE
    url = f"{base}/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": SIGNAL_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,
        },
    }

    data = await _do_gemini_http(url, payload, settings.google_api_key)
    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    meta = data.get("usageMetadata", {})
    usage = {
        "input_tokens": meta.get("promptTokenCount", 0),
        "output_tokens": meta.get("candidatesTokenCount", 0),
        "cache_read_tokens": 0,
    }
    return raw, usage


def _clean_json(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


async def generate_signal(
    symbol: str,
    market: str,
    episode_id: str,
    recent_candles: list[dict],
    indicators: dict,
    active_strategies: list[str],
    recent_signals: list[dict],
    knowledge_snippets: list[str],
    historical_snippets: list[str] | None = None,
    upcoming_events: list[dict] | None = None,
) -> dict | None:
    lock_key = f"signal_lock:{market}:{symbol}"
    if not await redis_client.set_lock(lock_key, settings.signal_cooldown_seconds):
        log.debug("signal_cooldown_active", symbol=symbol)
        return None

    # Read runtime config — model and depth may have changed via UI
    bot_config = await redis_client.get_bot_config()
    model = bot_config.get("signal_model", settings.claude_model)
    depth = bot_config.get("prompt_depth", "standard")
    depth_config = PROMPT_DEPTH_CONFIG.get(depth, PROMPT_DEPTH_CONFIG["standard"])
    max_tokens = depth_config["max_tokens"]

    candles_to_send = recent_candles[-depth_config["candles"]:]

    user_prompt = await build_signal_prompt(
        symbol, market, candles_to_send, indicators,
        active_strategies, recent_signals, knowledge_snippets,
        depth=depth,
        historical_snippets=historical_snippets,
        upcoming_events=upcoming_events,
    )

    provider = _MODEL_PROVIDER.get(model, "anthropic")

    try:
        if provider == "google":
            raw, usage = await _call_gemini(model, max_tokens, user_prompt)
        else:
            raw, usage = await _call_anthropic(model, max_tokens, user_prompt)

        await track_usage(model, "signal", usage, market=market, episode_id=episode_id)

        signal_data = json.loads(_clean_json(raw))
        log.info("signal_generated", symbol=symbol, model=model, provider=provider,
                 depth=depth, action=signal_data.get("action"),
                 confidence=signal_data.get("confidence"))
        return signal_data

    except Exception as e:
        log.error("signal_generation_failed", symbol=symbol, model=model, error=str(e))
        return None
