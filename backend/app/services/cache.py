"""Redis cache for per-tenant query embeddings.

Cuts embedding API cost + latency for repeated queries. Key strategy (approved):
sha256 of the normalized query, namespaced by model + tenant, so no tenant can
ever hit another tenant's cache line. Redis is the shared cache/session layer,
so all API replicas share it — no per-instance cache state.
"""
import hashlib
import json

import redis.asyncio as aioredis

from app.config import Settings


def cache_key(settings: Settings, tenant_id: str, query: str) -> str:
    normalized = " ".join(query.lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"embed:{settings.embedding_model}:{tenant_id}:{digest}"


def _redis(settings: Settings):
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def get_cached_embedding(
    settings: Settings, tenant_id: str, query: str
) -> list[float] | None:
    r = _redis(settings)
    try:
        raw = await r.get(cache_key(settings, tenant_id, query))
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001 — a cache miss must not break the chat path
        return None
    finally:
        await r.aclose()


async def set_cached_embedding(
    settings: Settings, tenant_id: str, query: str, vector: list[float]
) -> None:
    r = _redis(settings)
    try:
        await r.set(
            cache_key(settings, tenant_id, query),
            json.dumps(vector),
            ex=settings.embedding_cache_ttl,
        )
    finally:
        await r.aclose()