"""Embedding backends — TEI (default) or OpenAI.

From Phase 8 the embedding provider is pluggable. The default backend is a
Hugging Face Text Embeddings Inference (TEI) endpoint — or any
OpenAI-compatible /v1/embeddings service — serving an open-source model
(default BAAI/bge-base-en-v1.5, 768-d). The OpenAI backend is retained as a
drop-in fallback so we can roll back without a code change.

TEI exposes an OpenAI-compatible /v1/embeddings route, so both backends reuse
the same AsyncOpenAI batching code; only base_url/auth differ.

bge-family models retrieve best when the QUERY carries an instruction prefix
and DOCUMENTS are encoded plain. `embed_texts(..., query=True)` applies that
prefix for retrieval queries; ingestion calls with `query=False` so chunk text
is stored unprefixed — the arrangement the model was fine-tuned for.

Clients are created per call (not cached) so each stays bound to the calling
asyncio loop — the Celery worker runs tasks in fresh loops and a cached client
would be tied to a closed one.
"""
from openai import AsyncOpenAI

from app.config import Settings

# bge-family query instruction — applied to retrieval queries only. Irrelevant
# for non-bge models (e.g. the OpenAI fallback), where no prefix is used.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

# OpenAI caps embeddings at 2048 inputs per request; chunk well under that.
_BATCH_SIZE = 128


async def embed_texts(
    settings: Settings, texts: list[str], *, query: bool = False
) -> list[list[float]]:
    """Embed a list of strings; returns vectors in the same input order.

    `query=True` marks a retrieval query and applies the model's query-side
    instruction prefix (bge) so the query encodes the way the model ranks
    documents. Ingestion passes the default False so document chunks stay plain.
    """
    if not texts:
        return []

    instruction = ""
    if query and "bge" in settings.embedding_model.lower():
        instruction = BGE_QUERY_INSTRUCTION
    source = [instruction + t for t in texts]

    if settings.embedding_backend == "tei":
        return await _embed_tei(settings, source)
    if settings.embedding_backend == "openai":
        return await _embed_openai(settings, source)
    raise ValueError(f"Unsupported embedding_backend: {settings.embedding_backend!r}")


def _client(*, tei: bool, settings: Settings) -> AsyncOpenAI:
    """Build the OpenAI-compatible client for the chosen backend."""
    if tei:
        if not settings.tei_url:
            raise RuntimeError(
                "TEI_URL is not set — configure it to generate embeddings."
            )
        # TEI ignores the auth key on the OpenAI-compatible route; "EMPTY" keeps
        # the signature uniform so both backends share the calling code.
        return AsyncOpenAI(base_url=settings.tei_url, api_key="EMPTY")
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set — configure it to generate embeddings."
        )
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def _embed_tei(settings: Settings, texts: list[str]) -> list[list[float]]:
    client = _client(settings=settings, tei=True)
    try:
        return await _embed(client, settings.embedding_model, texts)
    finally:
        await client.close()


async def _embed_openai(
    settings: Settings, texts: list[str]
) -> list[list[float]]:
    client = _client(settings=settings, tei=False)
    try:
        return await _embed(client, settings.embedding_model, texts)
    finally:
        await client.close()


async def _embed(
    client: AsyncOpenAI, model: str, texts: list[str]
) -> list[list[float]]:
    """Batch-embed `texts`, preserving order. Shared by both backends."""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        resp = await client.embeddings.create(model=model, input=batch)
        vectors.extend(d.embedding for d in resp.data)
    return vectors