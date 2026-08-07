"""Per-API-key rate limiting (Phase 5): Redis sliding-window log.

The Phase 2 stub is replaced with a real, horizontally-safe limiter. Every
protected request goes through `require_api_key`, which calls `allow()`.

Algorithm (sliding window log, no Redis module required):
  * One sorted set per limit-scope key, `rl:{plan}:{api_key_hash}`.
  * Member = a request timestamp (with a random suffix so identical wall-clock
    requests don't collide in the same second).
  * On each request: purge entries older than the window (ZREMRANGEBYSCORE),
    count survivors (ZCARD). If count >= limit -> deny; else ZADD the new
    timestamp and touch EXPIRE so unused keys garbage-collect.

Fidelity notes:
  * We key on the sha256 api_key_hash (not the tenant id) so each distinct key
    gets its own budget — one noisy key can't drain the whole tenant.
  * Limits come from the tenant's `rate_limit_plan` via `rate_limits_csv`, so
    tier changes are config-only (no schema migration).
  * We run a small read-then-write (purge+count, then add). Concurrent requests
    can marginally overshoot the cap; if exactness matters later, move the core
    into a Lua script (INCRBY-style) — fine for per-key budgets today.
  * On any Redis error we FAIL OPEN (allow) by default: a cache/limiter outage
    must never blackout the product. `rate_limit_fail_open=false` flips that.
"""
import logging
import secrets
import time
from dataclasses import dataclass

import redis.asyncio as aioredis

from app.config import Settings, get_settings
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int | None = None
    retry_after: int | None = None
    message: str = "rate limit exceeded"


def parse_rate_limits(csv: str) -> dict[str, tuple[int, int]]:
    """Parse `rate_limits_csv` into {plan: (limit, window_seconds)}."""
    out: dict[str, tuple[int, int]] = {}
    for item in (csv or "").split(","):
        item = item.strip()
        if not item or "=" not in item or "/" not in item:
            continue
        plan, spec = item.split("=", 1)
        limit_s, window_s = spec.split("/", 1)
        try:
            out[plan.strip()] = (int(limit_s.strip()), int(window_s.strip()))
        except ValueError:
            logger.warning("Ignoring malformed rate-limit entry: %r", item)
    if "free" not in out:
        out["free"] = (10, 60)
    return out


class RateLimiter:
    """Redis sliding-window limiter keyed on the tenant's API-key hash.

    `_redis_client()` is a seam so tests can inject a fake without hitting
    Redis. The client is created lazily and reused (connection pooling).
    """

    def __init__(
        self, settings: Settings | None = None, fail_open: bool | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.fail_open = (
            self.settings.rate_limit_fail_open if fail_open is None else fail_open
        )
        self.plan_limits = parse_rate_limits(self.settings.rate_limits_csv)
        self._client = None

    @staticmethod
    def _key(plan: str, api_key_hash: str) -> str:
        return f"rl:{plan}:{api_key_hash}"

    def _redis_client(self):
        if self._client is None:
            self._client = aioredis.from_url(
                self.settings.redis_url, decode_responses=True
            )
        return self._client

    async def _close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def allow(self, tenant: Tenant) -> RateLimitResult:
        plan = (tenant.rate_limit_plan or "free").strip() or "free"
        limit, window = self.plan_limits.get(plan, self.plan_limits["free"])
        key = self._key(plan, tenant.api_key_hash)
        now = time.time()
        window_start = int(now - window)

        try:
            r = self._redis_client()
            # Purge expired entries, then count what remains in the window.
            await r.zremrangebyscore(key, 0, window_start)
            count = int((await r.zcard(key)) or 0)

            if count >= limit:
                oldest = await r.zrange(key, 0, 0, withscores=True)
                retry_after = window  # conservative default
                if oldest:
                    # Redis returns (member, score); score may be a str under
                    # decode_responses, so coerce defensively.
                    score = float(oldest[0][1])
                    retry_after = max(1, int(window - (now - score)))
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after=retry_after,
                    message=(
                        f"Rate limit exceeded for this key "
                        f"({limit} requests / {window}s). Retry in {retry_after}s."
                    ),
                )

            # Unique member: timestamp + random suffix so equal wall-clock
            # requests are distinct set members.
            member = f"{now}.{secrets.token_hex(3)}"
            pipe = r.pipeline()
            pipe.zadd(key, {member: float(now)})
            pipe.expire(key, window)
            await pipe.execute()

            return RateLimitResult(
                allowed=True, remaining=max(0, limit - count - 1)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Rate limiter error: %s", exc, exc_info=True)
            if not self.fail_open:
                raise
            return RateLimitResult(allowed=True, remaining=None)


class AllowAllLimiter:
    """Test/CI limp-ahead: never blocks, used to keep routes off Redis in tests."""

    async def allow(self, tenant: Tenant) -> RateLimitResult:
        return RateLimitResult(allowed=True, remaining=None, message="")


_rate_limiter: RateLimiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


def set_rate_limiter(limiter) -> None:
    global _rate_limiter
    _rate_limiter = limiter