"""
Unified multi-LLM caller for the forecast ensemble + research/post-mortem agents.

Replaces signal_generator.py's call logic, generalized to 4 providers:
Anthropic (SDK), Google Gemini (raw REST, rate-limited), OpenAI + DeepSeek
(both via raw httpx — DeepSeek is OpenAI-wire-compatible, so one function
serves both and we avoid adding the `openai` SDK as a dependency).

call_role() is the single entry point used by prediction/ensemble.py,
agents/research_agent.py, and agents/postmortem_agent.py.
"""
import asyncio
import json
import time
import httpx
import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
from app.services.cost_tracker import track_usage

log = structlog.get_logger()

_anthropic_client: AsyncAnthropic | None = None

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",  # OpenAI-wire-compatible
}

_PROVIDER_KEY_FIELDS = {
    "anthropic": "anthropic_api_key",
    "google": "google_api_key",
    "openai": "openai_api_key",
    "deepseek": "deepseek_api_key",
}

# ── Gemini rate limiter — verbatim reuse of signal_generator.py's pattern ──────
# Free tier: 15 RPM. We schedule calls at fixed intervals to stay safe.
# Callers atomically claim a time slot, then wait outside the lock.
_gemini_slot_lock = asyncio.Lock()
_gemini_next_slot: float = 0.0
_GEMINI_SLOT_INTERVAL = 7.0  # seconds between calls (~8 RPM, safe under 15 RPM free tier)


async def _claim_gemini_slot() -> float:
    """Return the monotonic time at which this caller may fire its request."""
    global _gemini_next_slot
    loop = asyncio.get_event_loop()
    async with _gemini_slot_lock:
        now = loop.time()
        slot = max(now, _gemini_next_slot)
        _gemini_next_slot = slot + _GEMINI_SLOT_INTERVAL
        return slot


def has_key_for_provider(provider: str) -> bool:
    field = _PROVIDER_KEY_FIELDS.get(provider)
    if not field:
        return False
    return bool(getattr(settings, field, "") or "")


def get_anthropic_client() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=30))
async def _call_anthropic_raw(model: str, system_prompt: str, user_prompt: str, max_tokens: int) -> tuple[str, object]:
    response = await get_anthropic_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
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


async def _call_gemini_raw(model: str, system_prompt: str, user_prompt: str, max_tokens: int) -> tuple[str, dict]:
    if not settings.google_api_key:
        raise ValueError("GOOGLE_API_KEY is not configured.")

    slot = await _claim_gemini_slot()
    wait = slot - asyncio.get_event_loop().time()
    if wait > 0:
        await asyncio.sleep(wait)

    url = f"{GEMINI_API_BASE}/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=30))
async def _do_openai_compatible_http(url: str, payload: dict, api_key: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        if not resp.is_success:
            log.warning("openai_compatible_http_error", url=url, status=resp.status_code, body=resp.text[:300])
        resp.raise_for_status()
        return resp.json()


async def call_anthropic(model: str, system_prompt: str, user_prompt: str, max_tokens: int) -> tuple[str, dict]:
    """Returns (raw_text, usage_dict)."""
    raw, usage = await _call_anthropic_raw(model, system_prompt, user_prompt, max_tokens)
    usage_dict = {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
    }
    return raw, usage_dict


async def call_gemini(model: str, system_prompt: str, user_prompt: str, max_tokens: int) -> tuple[str, dict]:
    return await _call_gemini_raw(model, system_prompt, user_prompt, max_tokens)


async def call_openai_compatible(
    provider: str, model: str, system_prompt: str, user_prompt: str, max_tokens: int, api_key: str
) -> tuple[str, dict]:
    """Shared HTTP code path for OpenAI + DeepSeek (DeepSeek is OpenAI-wire-compatible)."""
    url = PROVIDER_BASE_URLS.get(provider)
    if not url:
        raise ValueError(f"Unknown openai-compatible provider: {provider}")
    if not api_key:
        raise ValueError(f"No API key configured for provider {provider}")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    data = await _do_openai_compatible_http(url, payload, api_key)
    raw = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    usage_dict = {
        "input_tokens": usage.get("prompt_tokens", 0) or 0,
        "output_tokens": usage.get("completion_tokens", 0) or 0,
        "cache_read_tokens": 0,
    }
    return raw, usage_dict


async def call_role(role_config: dict, system_prompt: str, user_prompt: str) -> dict:
    """
    Single entry point for an ensemble role / agent call.

    role_config: {"role": str, "provider": str, "model": str, ...}

    Returns:
        {probability, reasoning, status: ok|skipped_no_key|error|timeout, latency_ms, usage}

    Empty API key for that provider -> status='skipped_no_key', no network call
    (graceful degradation — UI shows this distinctly from an error).
    """
    role = role_config.get("role", "unknown")
    provider = role_config.get("provider", "anthropic")
    model = role_config.get("model") or role_config.get("default_model", "")
    max_tokens = role_config.get("max_tokens", 500)

    if not has_key_for_provider(provider):
        return {
            "probability": None,
            "reasoning": None,
            "status": "skipped_no_key",
            "latency_ms": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0},
        }

    start = time.monotonic()
    try:
        if provider == "anthropic":
            raw, usage = await call_anthropic(model, system_prompt, user_prompt, max_tokens)
        elif provider == "google":
            raw, usage = await call_gemini(model, system_prompt, user_prompt, max_tokens)
        elif provider in ("openai", "deepseek"):
            api_key = getattr(settings, _PROVIDER_KEY_FIELDS[provider], "")
            raw, usage = await call_openai_compatible(provider, model, system_prompt, user_prompt, max_tokens, api_key)
        else:
            raise ValueError(f"Unknown provider: {provider}")

        latency_ms = int((time.monotonic() - start) * 1000)

        await track_usage(model, f"forecast_{role}", usage, market="prediction", episode_id=None)

        parsed = json.loads(_clean_json(raw))
        probability = parsed.get("probability")
        if probability is not None:
            probability = max(0.0, min(1.0, float(probability)))
        reasoning = parsed.get("reasoning", "")

        return {
            "probability": probability,
            "reasoning": reasoning,
            "status": "ok",
            "latency_ms": latency_ms,
            "usage": usage,
        }
    except (httpx.TimeoutException, asyncio.TimeoutError):
        latency_ms = int((time.monotonic() - start) * 1000)
        log.warning("call_role_timeout", role=role, provider=provider, model=model)
        return {
            "probability": None,
            "reasoning": None,
            "status": "timeout",
            "latency_ms": latency_ms,
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0},
        }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        log.error("call_role_failed", role=role, provider=provider, model=model, error=str(e))
        return {
            "probability": None,
            "reasoning": None,
            "status": "error",
            "latency_ms": latency_ms,
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0},
            "error_detail": str(e)[:500],
        }
