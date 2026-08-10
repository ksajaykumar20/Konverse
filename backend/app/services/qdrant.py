"""Qdrant vector-store operations.

Layout (confirmed in Phase 3): ONE shared collection; every point's payload
carries `tenant_id`, and every read filters strictly by it. This keeps
multi-tenancy correct while the collection scale to a Qdrant cluster.

In addition to an HTTP server (production), two local, no-Docker modes are
supported so the whole stack runs on one box:
  * a filesystem path (e.g. "./qdrant") -> on-disk local Qdrant, persists
    across restarts, each client open/reopen reads/writes the same directory;
  * ":memory:" -> in-process. Obvious — this is actually the default Qdrant local
    :memory: store, but each AsyncQdrantClient instance gets a FRESH empty store,
    so per-call opens would lose data. For that mode we return a SHARED singleton
    (module-global) so every portal sees the same points until process exit.

The per-call open/close pattern holds in every mode: disk mode persists to the
directory, and the :memory: singleton is closed only on process teardown.
"""
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import Settings

# Shared client for `:memory:` local mode. The default Qdrant local "in-memory"
# store is tied to a single client instance, so every caller must reuse this one
# or each open would start empty. Disk-pathed mode does NOT use this — it creates
# a fresh client per call bound to the path.
_inmemory_client: AsyncQdrantClient | None = None


def _is_local(qdrant_url: str) -> bool:
    """True when qdrant_url selects a no-server local store (a filesystem path
    or `:memory:`).

    The only non-local form is an http(s) URL pointing at a Qdrant server; every
    other value — relative (`./qdrant_local`), absolute (`C:\\data\\qdrant` or
    `/var/lib/qdrant`), or `:memory:` — is served locally by the client.
    """
    return not (
        qdrant_url.startswith("http://") or qdrant_url.startswith("https://")
    )


def _client(settings: Settings) -> AsyncQdrantClient:
    global _inmemory_client
    url = settings.qdrant_url

    if url == ":memory:":
        if _inmemory_client is None:
            _inmemory_client = AsyncQdrantClient(location=":memory:")
        return _inmemory_client

    if _is_local(url):
        # On-disk local mode: pass the path to `path=` so Qdrant persists to it.
        # (Note: `location=` is only for ":memory:"; unknown string values there
        # are interpreted as an HTTP URL, hence the two distinct kwargs.)
        return AsyncQdrantClient(path=url)

    return AsyncQdrantClient(url=url)


async def close_client(client: AsyncQdrantClient, settings: Settings) -> None:
    """Close a client, unless it is the shared `:memory:` singleton.

    The shared in-memory store must outlive individual calls — closing it here
    would wipe every tenant's vectors. All other modes (disk path, HTTP server)
    are per-call and safe to close after use.
    """
    if settings.qdrant_url == ":memory:" and client is _inmemory_client:
        return
    await client.close()


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
        await close_client(client, settings)


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
        await close_client(client, settings)


async def delete_tenant_points(settings: Settings, tenant_id: str) -> None:
    """Delete every vector owned by a tenant. Used by admin hard-delete.

    Qdrant deletions are filtered by the `tenant_id` payload field (the same
    key retrieval filters on), so only that tenant's points are removed.
    """
    client = _client(settings)
    try:
        await client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id", match=MatchValue(value=tenant_id)
                        )
                    ]
                )
            ),
        )
    finally:
        await close_client(client, settings)