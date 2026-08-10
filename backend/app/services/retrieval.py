"""RAG retrieval: embed the query, then search tenant-filtered Qdrant chunks.

Tenant isolation is enforced at the query level: every search carries a
`tenant_id == <tenant>` filter, so a tenant can never retrieve another tenant's
vectors regardless of how the query is phrased (verified by the Phase 4
isolation test).
"""
from dataclasses import dataclass

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import Settings
from app.services import cache, embeddings, qdrant


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
    # query=True applies the bge query-side instruction prefix, matching how
    # bge-family models rank documents during training.
    vector = (await embeddings.embed_texts(settings, [query], query=True))[0]
    await cache.set_cached_embedding(settings, tenant_id, query, vector)
    return vector


async def _search_qdrant(
    settings: Settings, tenant_id: str, query_vector: list[float]
):
    """Raw Qdrant search scoped to one tenant. Kept for testability.

    Uses the shared `qdrant._client` so local (on-disk / :memory:) modes are
    hit correctly instead of a hard-coded HTTP URL.
    """
    client = qdrant._client(settings)
    try:
        qfilter = Filter(
            must=[
                FieldCondition(
                    key="tenant_id", match=MatchValue(value=str(tenant_id))
                )
            ]
        )
        # qdrant-client >=1.11 renamed the top-level `.search()` to
        # `.query_points()` (same purpose, different wrapper). It returns a
        # `QueryResponse` with `.points`. Accept both shapes defensively in
        # case the dependency is pinned to an older release.
        response = await client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            query_filter=qfilter,
            limit=settings.retrieval_top_k,
            with_payload=True,
        )
        return response.points if hasattr(response, "points") else response
    finally:
        await qdrant.close_client(client, settings)


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