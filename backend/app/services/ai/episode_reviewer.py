"""
Post-episode analysis: Claude generates lessons and a generation summary.
"""
import json
import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
from app.services.ai.prompt_builder import REVIEW_SYSTEM_PROMPT, build_review_prompt
from app.services.cost_tracker import track_usage

log = structlog.get_logger()

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "lessons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "regime": {"type": "string"},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["title", "body", "regime", "importance"],
            },
        },
        "generation": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "kelly_fraction": {"type": "number"},
                "max_leverage": {"type": "integer"},
                "promote_strategies": {"type": "array", "items": {"type": "string"}},
                "retire_strategies": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "kelly_fraction", "max_leverage", "promote_strategies", "retire_strategies"],
        },
    },
    "required": ["lessons", "generation"],
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
async def review_episode(
    episode: dict,
    trades: list[dict],
    existing_lessons: list[str],
) -> dict:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_prompt = build_review_prompt(episode, trades, existing_lessons)

    model = settings.claude_model
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    if hasattr(response, "usage"):
        await track_usage(model, "episode_review", response.usage,
                          market=episode.get("market", "all"),
                          episode_id=episode.get("id"))

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        result = json.loads(raw)
        log.info("episode_review_complete",
                 lessons=len(result.get("lessons", [])),
                 gen_summary=result.get("generation", {}).get("summary", "")[:80])
        return result
    except json.JSONDecodeError as e:
        log.error("episode_review_parse_failed", error=str(e), raw=raw[:200])
        raise
