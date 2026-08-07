"""RAG retrieval: embed the query, then search tenant-filtered Qdrant chunks.

Tenant isolation is enforced at the query level: every search carries a
`tenant_id == <tenant>` filter, so a tenant can never retrieve another tenant's
vectors regardless of how the query is phrased (verified by the Phase 4
isolation test).
"""
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import Settings
from app.services import cache, embeddings


@dataclass
class RetrievalResult:
    chunks: list[dict]  # [{text, score, document_id}, ...] sorted by score desc
    max_score: float


async def _embed_query(
    settings: Settings, tenant_id: str, query: str
) -> list[float]:
    """Embed `query`, using the Redis cache when available."""
    cached = await cache.get_cached_embedding(settings, tenant_id, query)
    if cached is not None:
        return cached
    vector = (await embeddings.embed_texts(settings, [query]))[0]
    await cache.set_cached_embedding(settings, tenant_id, query, vector)
    return vector


async def _search_qdrant(
    settings: Settings, tenant_id: str, query_vector: list[float]
):
    """Raw Qdrant search scoped to one tenant. Extracted for testability."""
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        qfilter = Filter(
            must=[
                FieldCondition(
                    key="tenant_id", match=MatchValue(value=str(tenant_id))
                )
            ]
        )
        result = await client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_vector,
            query_filter=qfilter,
            limit=settings.retrieval_top_k,
            with_payload=True,
        )
        # qdrant-client 1.x returns a list; newer wraps in a result object.
        return result.points if hasattr(result, "points") else result
    finally:
        await client.close()


async def retrieve(
    settings: Settings, tenant_id: str, query: str
) -> RetrievalResult:
    """Return the tenant's top-k chunks for `query` plus the max similarity."""
    query_vector = await _embed_query(settings, tenant_id, query)
    points = await _search_qdrant(settings, tenant_id, query_vector)

    chunks: list[dict] = []
    max_score = 0.0
    for p in points:
        payload = p.payload or {}
        score = float(getattr(p, "score", 0.0) or 0.0)
        chunks.append(
            {
                "text": payload.get("text", ""),
                "score": score,
                "document_id": payload.get("document_id"),
            }
        )
        max_score = max(max_score, score)
    return RetrievalResult(chunks=chunks, max_score=max_score)