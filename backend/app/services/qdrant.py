"""Qdrant vector-store operations.

Layout (approved in Phase 3): ONE shared collection; every point's payload
carries `tenant_id`, and every read filters strictly by it. This keeps
multi-tenancy correct while letting the collection scale to a Qdrant cluster.
"""
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import Settings


def _client(settings: Settings) -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url)


async def ensure_collection(settings: Settings) -> None:
    """Create the tenant-tagged collection if it doesn't exist yet."""
    client = _client(settings)
    try:
        collections = await client.get_collections()
        names = {c.name for c in collections.collections}
        if settings.qdrant_collection not in names:
            await client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(
                    size=settings.embedding_size, distance=Distance.COSINE
                ),
            )
    finally:
        await client.close()


async def upsert_document_vectors(
    settings: Settings,
    tenant_id: str,
    document_id: str,
    texts: list[str],
    vectors: list[list[float]],
) -> None:
    """Upsert one document's chunk vectors, tagged with tenant + document id."""
    if not texts or len(texts) != len(vectors):
        raise ValueError("texts and vectors must be non-empty and equal length")

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vectors[i],
            payload={
                "tenant_id": str(tenant_id),
                "document_id": str(document_id),
                "chunk_index": i,
                "text": texts[i],
            },
        )
        for i in range(len(texts))
    ]

    client = _client(settings)
    try:
        await client.upsert(
            collection_name=settings.qdrant_collection, points=points
        )
    finally:
        await client.close()