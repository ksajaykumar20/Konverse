"""Embedding backends — TEI (default), OpenAI, or local ONNX via fastembed.

From Phase 8 the embedding provider is pluggable. The default backend is a
Hugging Face Text Embeddings Inference (TEI) endpoint — or any
OpenAI-compatible /v1/embeddings service — serving an open-source model
(default BAAI/bge-base-en-v1.5, 768-d). The OpenAI backend is retained as a
drop-in fallback so we can roll back without a code change.

The `local` backend runs fastembed (ONNX, CPU) with NO provider key and NO
server — it downloads a small ONNX model on first use, then embeds in a worker
thread. This powers the Docker-free local stack.

TEI exposes an OpenAI-compatible /v1/embeddings route, so the two remote
backends reuse the same AsyncOpenAI batching code; only base_url/auth differ.

bge-family models retrieve best when the QUERY carries an instruction prefix
and DOCUMENTS are encoded plain. `embed_texts(..., query=True)` applies that
prefix for retrieval queries; ingestion calls with `query=False` so chunk text
is stored unprefixed — the arrangement the model was fine-tuned for.

Remote clients are created per call (not cached) so each stays bound to the
calling asyncio loop — the Celery worker runs tasks in fresh loops and a cached
client would be tied to a closed one. The local embedder is intentionally a
process-global singleton: fastembed model load is expensive, and the model is
thread-safe for embed calls.
"""
import asyncio

from openai import AsyncOpenAI

from app.config import Settings

# bge-family query instruction — applied to retrieval queries only. Irrelevant
# for non-bge models (e.g. the OpenAI or local fallbacks), where no prefix is used.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

# OpenAI caps embeddings at 2048 inputs per request; chunk well under that.
_BATCH_SIZE = 128

# Lazy-loaded, process-global fastembed instance (guarded by a lock for first load).
_local_embedder: object | None = None
_local_embedder_lock: asyncio.Lock = asyncio.Lock()


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
    if settings.embedding_backend == "local":
        return await _embed_local(settings, source)
    raise ValueError(f"Unsupported embedding_backend: {settings.embedding_backend!r}")


async def _get_local_embedder(settings: Settings):
    """Return the shared fastembed instance, loading it once under a lock."""
    global _local_embedder
    if _local_embedder is None:
        async with _local_embedder_lock:
            if _local_embedder is None:
                from fastembed import TextEmbedding

                _local_embedder = TextEmbedding(model_name=settings.embedding_model)
    return _local_embedder


async def _embed_local(
    settings: Settings, texts: list[str]
) -> list[list[float]]:
    """Embed with on-device fastembed, running the CPU-bound pass in a thread.

    fastembed `embed` is a synchronous generator over its inputs; we collect
    into a list inside the worker thread so we never block the event loop.
    """
    embedder = await _get_local_embedder(settings)

    def _run() -> list[list[float]]:
        # Coerce numpy.float32 -> plain Python float. Downstream (the Redis
        # embedding cache JSON-serializes vectors, and Qdrant expects floats)
        # can't handle the numpy scalar types that onnxruntime returns.
        return [[float(x) for x in vec] for vec in embedder.embed(texts)]

    return await asyncio.to_thread(_run)


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