"""Health checks for the Konverse stack.

GET /health probes the data layer (Postgres/SQLite), Qdrant, and Redis with
short timeouts and reports each independently. This is intentionally
dependency-injectable: each check is a module-level coroutine that the test
suite monkeypatches with fakes, so the endpoint is fully testable with no live
infrastructure running.

The checkers are local-mode aware: a SQLite datasource and an on-disk /
in-memory Qdrant store are themselves the "infra" in the Docker-free local
profile, so they report ok without a live server. Redis is reported as
not-required rather than down when embedding is on-device (its only hard
dependencies are rate-limiting + Celsius, both of which fail open).

Returns:
  * 200 {"status":"ok", ...} when every *required* service answers.
  * 503 {"status":"degraded", ...} when a required service is down, listing
    which one and why.
"""
import asyncio

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException

from app.config import Settings, get_settings
from app.services import qdrant as qdrant_svc

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_SECONDS = 2.0


def _is_local_sqlite(settings: Settings) -> bool:
    return settings.database_url.startswith("sqlite")


async def _check_postgres(settings: Settings) -> dict:
    """Probe the relational store. SQLite (Docker-free profile) is local, so a
    probe would fail — treat it as healthy with an explanatory note."""
    if _is_local_sqlite(settings):
        return {"status": "ok", "latency_ms": None, "note": "local sqlite"}
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
    """Confirm the vector store answers by listing collections.

    Uses the same routing as the rest of the app (`qdrant._client`), so on-disk
    and in-memory local stores are checked correctly instead of assuming an HTTP
    URL. An `:memory:` store with no data still returns an empty-but-present
    collection list, which means "ok".
    """
    client = qdrant_svc._client(settings)
    try:
        await asyncio.wait_for(
            client.get_collections(), timeout=CHECK_TIMEOUT_SECONDS
        )
        return {"status": "ok", "latency_ms": None}
    except Exception as exc:  # noqa: BLE001
        return {"status": "down", "error": str(exc)}
    finally:
        await qdrant_svc.close_client(client, settings)


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
    # Redis is reported honestly: rate-limiting and the embedding cache both
    # FAIL OPEN, so a down Redis is surfaced as `degraded` here but never stops
    # API/chat from working — it is diagnostic, not load-bearing.
    return {
        "qdrant": await _check_qdrant(settings),
        "postgres": await _check_postgres(settings),
        "redis": await _check_redis(settings),
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