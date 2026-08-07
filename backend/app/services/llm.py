"""Anthropic Claude streaming for the chat path (claude-sonnet-4-6).

The client is created per call so it binds to the caller's asyncio loop — the
API runs one loop per process; correctness here matters for the Celery worker
too, which spins a fresh loop per task.
"""
import logging

from anthropic import AsyncAnthropic

from app.config import Settings

logger = logging.getLogger(__name__)


async def stream_answer(
    settings: Settings, system_prompt: str, user_message: str
) -> "AsyncGenerator[str, None]":
    """Yield text deltas from Claude for the grounded turn."""
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — configure it to chat."
        )

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": user_message}]

    try:
        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.llm_max_tokens,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for delta in stream.text_stream:
                yield delta
    except Exception as exc:  # noqa: BLE001 — surface to SSE as an error event
        logger.error("LLM stream error: %s", exc)
        raise