"""Health checks for the Konverse stack.

GET /health probes Postgres, Qdrant, and Redis with short timeouts and reports
each independently. This is intentionally dependency-injectable: each check is
a module-level coroutine that the test suite monkeypatches with fakes, so the
endpoint is fully testable with no live infrastructure running.

Returns:
  * 200 {"status":"ok", ...} when every service answers.
  * 503 {"status":"degraded", ...} when at least one service is down, listing
    which one and why.
"""
import asyncio

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from qdrant_client import AsyncQdrantClient

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 2.0


async def _check_postgres(settings: Settings) -> dict:
    """Connect to Postgres and run a trivial query. Async for non-blocking API."""
    try:
        conn = await asyncpg.connect(
            settings.database_url, timeout=CHECK_TIMEOUT_SECONDS
        )
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return {"status": "ok", "latency_ms": None}
    except Exception as exc:  # noqa: BLE001 — surface any failure to /health
        return {"status": "down", "error": str(exc)}


async def _check_qdrant(settings: Settings) -> dict:
    """Confirm Qdrant is reachable by listing collections."""
    client = AsyncQdrantClient(url=settings.qdrant_url)
    try:
        await asyncio.wait_for(client.get_collections(), timeout=CHECK_TIMEOUT_SECONDS)
        return {"status": "ok", "latency_ms": None}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": str(exc)}
    finally:
        await client.close()


async def _check_redis(settings: Settings) -> dict:
    """PING Redis (used as cache + Celery broker)."""
    r = aioredis.from_url(settings.redis_url, socket_timeout=CHECK_TIMEOUT_SECONDS)
    try:
        await asyncio.wait_for(r.ping(), timeout=CHECK_TIMEOUT_SECONDS)
        return {"status": "ok", "latency_ms": None}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": str(exc)}
    finally:
        await r.aclose()


# Ordered, labelled checkers so the report is deterministic and readable.
async def _run_checks(settings: Settings) -> dict[str, dict]:
    results = await asyncio.gather(
        _check_postgres(settings),
        _check_qdrant(settings),
        _check_redis(settings),
    )
    return {
        "postgres": results[0],
        "qdrant": results[1],
        "redis": results[2],
    }


@router.get("/health")
async def health() -> dict:
    """Aggregate health of the backend's external dependencies.

    200 with `status: ok` when every service answers; 503 with `status:
    degraded` and per-service detail when any is down, so load balancers /
    orchestrators can take this instance out of rotation.
    """
    settings = get_settings()
    checks = await _run_checks(settings)
    all_ok = all(c["status"] == "ok" for c in checks.values())

    payload = {"status": "ok" if all_ok else "degraded", "checks": checks}
    if not all_ok:
        raise HTTPException(status_code=503, detail=payload)
    return payload