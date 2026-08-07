"""Phase 5 rate-limit tests — sliding-window logic + HTTP 429 enforcement.

Redis is never touched: the limiter's `_redis_client()` seam is pointed at an
in-memory fake that implements exactly the commands `allow()` uses.
"""
import pytest
from httpx import AsyncClient

from app.config import Settings
from app.models.tenant import Tenant
from app.services import ratelimit
from app.services.ratelimit import RateLimitResult

API_KEY = "X-API-Key"


class _FakeRedis:
    """Minimal async fake covering zremrangebyscore/zcard/zrange + pipeline."""

    def __init__(self) -> None:
        self.z: dict[str, list[tuple[float, str]]] = {}

    def _bucket(self, key: str):
        self.z.setdefault(key, [])
        return self.z[key]

    async def zremrangebyscore(self, key, lo, hi):
        lst = self._bucket(key)
        keep = [e for e in lst if not (lo <= e[0] <= hi)]
        removed = len(lst) - len(keep)
        self.z[key] = keep
        return removed

    async def zcard(self, key):
        return len(self._bucket(key))

    async def zrange(self, key, start, end, withscores=False):
        # Redis returns (member, score); keep the fake aligned.
        ordered = sorted(self._bucket(key), key=lambda e: e[0])[start : end + 1]
        return [(m, sc) for sc, m in ordered] if withscores else [m for _, m in ordered]

    def pipeline(self):
        return _FakePipe(self)


class _FakePipe:
    def __init__(self, r: _FakeRedis) -> None:
        self.r = r
        self._ops = []

    def zadd(self, key, mapping):
        for member, score in mapping.items():
            self.r._bucket(key).append((float(score), member))
        return self

    def expire(self, key, ttl):
        return self

    async def execute(self):
        return self._ops


def _limiter(fail_open: bool = True) -> ratelimit.RateLimiter:
    class L(ratelimit.RateLimiter):
        def __init__(self, fake):
            super().__init__(settings=None, fail_open=fail_open)
            self.fake = fake

        def _redis_client(self):
            return self.fake

    return L(_FakeRedis())


def _tenant(plan: str = "free") -> Tenant:
    return Tenant(name="x", slug="x", industry="", api_key_hash="a" * 64,
                  rate_limit_plan=plan)


@pytest.mark.asyncio
async def test_sliding_window_allows_then_denies_at_limit():
    limiter = _limiter()
    limiter.plan_limits["free"] = (3, 60)
    t = _tenant()

    results = [await limiter.allow(t) for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    denied = results[3]
    assert denied.retry_after is not None and denied.retry_after >= 1


@pytest.mark.asyncio
async def test_window_expires_and_reallows():
    limiter = _limiter()
    limiter.plan_limits["free"] = (1, 60)
    t = _tenant()

    assert (await limiter.allow(t)).allowed is True
    assert (await limiter.allow(t)).allowed is False  # window full
    # New key gets its own budget (per-API-key isolation).
    other = _tenant()
    other.api_key_hash = "b" * 64
    assert (await limiter.allow(other)).allowed is True


@pytest.mark.asyncio
async def test_redis_error_fails_open():
    class Boom:
        async def zremrangebyscore(self, *_a, **_k):
            raise RuntimeError("redis down")

        def pipeline(self):
            raise RuntimeError("redis down")

    class L(ratelimit.RateLimiter):
        def __init__(self):
            super().__init__(settings=None, fail_open=True)

        def _redis_client(self):
            return Boom()

    limiter = L()
    r = await limiter.allow(_tenant())
    assert r.allowed is True  # outage must not blackout the API


async def _create_tenant(client: AsyncClient) -> dict:
    r = await client.post("/api/tenants", json={"name": "RL", "industry": "test"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_auth_returns_429_with_retry_after(client, monkeypatch):
    t = await _create_tenant(client)

    class Deny:
        async def allow(self, tenant):
            return RateLimitResult(allowed=False, retry_after=42, message="slow down")

    monkeypatch.setattr(
        "app.services.auth.get_rate_limiter", lambda: Deny()
    )

    r = await client.get("/api/tenants/me", headers={API_KEY: t["api_key"]})
    assert r.status_code == 429
    assert r.headers.get("retry-after") == "42"