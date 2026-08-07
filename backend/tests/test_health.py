"""pytest tests for GET /health — run against mocked checks, no live infra."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.routers import health as health_router


def _settings() -> Settings:
    """Deterministic settings for tests (never read the real .env)."""
    return Settings(
        database_url="postgresql+asyncpg://x@localhost/x",
        qdrant_url="http://localhost:9999",
        qdrant_collection="test",
        redis_url="redis://localhost:9999/0",
    )


@pytest.fixture
async def client():
    app = create_app(_settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def healthy_check(monkeypatch):
    async def _ok(_settings):
        return {"status": "ok", "latency_ms": 1}
    monkeypatch.setattr(health_router, "_check_postgres", _ok)
    monkeypatch.setattr(health_router, "_check_qdrant", _ok)
    monkeypatch.setattr(health_router, "_check_redis", _ok)


@pytest.mark.asyncio
async def test_health_all_up_returns_200(client, healthy_check):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert all(c["status"] == "ok" for c in body["checks"].values())


@pytest.mark.asyncio
async def test_health_redis_down_returns_503(client, healthy_check, monkeypatch):
    async def _redis_down(_settings):
        return {"status": "down", "error": "connection refused"}
    monkeypatch.setattr(health_router, "_check_redis", _redis_down)

    resp = await client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()["detail"]
    assert body["status"] == "degraded"
    assert body["checks"]["redis"]["status"] == "down"
    assert body["checks"]["postgres"]["status"] == "ok"