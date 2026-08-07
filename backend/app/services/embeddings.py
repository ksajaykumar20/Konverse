"""OpenAI embeddings — text-embedding-3-small.

The client is created lazily per call so tests can patch `embed_texts` without
constructing a live client, and the worker (which runs its own asyncio loop)
gets a fresh client bound to that loop.
"""
from openai import AsyncOpenAI

from app.config import Settings

# OpenAI caps embeddings at 2048 strings per request — chunk well under that.
_BATCH_SIZE = 128


async def embed_texts(
    settings: Settings, texts: list[str]
) -> list[list[float]]:
    """Embed a list of strings; returns vectors in the same order.

    The client is built per call (not cached) so it stays bound to the calling
    asyncio loop — critical because the Celery worker runs each task in its own
    fresh loop and a cached client would be tied to a closed loop.
    """
    if not texts:
        return []
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set — configure it to generate embeddings."
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        resp = await client.embeddings.create(
            model=settings.embedding_model, input=batch
        )
        # OpenAI returns results in request order.
        vectors.extend(d.embedding for d in resp.data)
    return vectors