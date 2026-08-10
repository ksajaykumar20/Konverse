"""LLM backends for the chat path: Claude streaming or local extractive.

The `local` backend is the no-key, no-Docker fallback: instead of generating
new text, it GROUNDS the answer directly in the retrieved source by returning
the top-matching chunk verbatim, plus a short canned framing line. There is no
model, no API key, and nothing is streamed through a remote — every token is
deterministic and attributable (the "answer" is literally a cited passage).
"""
import logging

from app.config import Settings

logger = logging.getLogger(__name__)


def local_fallback_answer(chunks: list[dict]) -> str:
    """Build a cited, extractive answer from the top retrieved chunk.

    Used when `llm_backend == "local"`. Returns the highest-scoring chunk's text
    wrapped in a short attribution header so consumers see exactly which passage
    the answer came from. Empty if there are no chunks.
    """
    if not chunks:
        return "I don't have enough information in my sources to answer that."
    top = chunks[0]
    source = top.get("text", "").strip()
    if not source:
        return "I don't have enough information in my sources to answer that."
    score = float(top.get("score") or 0.0)
    return f'Based on my sources, here is the relevant passage:\n\n"{source}"'


async def stream_answer(
    settings: Settings,
    system_prompt: str,
    user_message: str,
    chunks: list[dict] | None = None,
) -> "AsyncGenerator[str, None]":
    """Yield text deltas for the grounded turn.

    Backend is selected by `settings.llm_backend`:
      * "local" — extractive, no key. `chunks` must be the retrieved passages
        (passed from the chat router); yields the cited answer as one delta.
      * "anthropic" — streams Claude deltas (needs ANTHROPIC_API_KEY).
    """
    if settings.llm_backend == "local":
        yield local_fallback_answer(chunks or [])
        return

    if settings.llm_backend != "anthropic":
        raise ValueError(
            f"Unsupported llm_backend: {settings.llm_backend!r}"
        )

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — configure it to chat."
        )

    from anthropic import AsyncAnthropic

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