"""Per-tenant rate limiting.

Phase 2 ships a no-op stub with the interface the auth dependency already
calls, so Phase 5 can swap in a Redis token-bucket implementation without
touching any router or the auth dependency.

The interface is intentionally small: given a tenant, answer whether a request
is allowed and report remaining budget. Plan/tier limits are read off the
tenant (`rate_limit_plan`) so limits map later to a billing/plan system.
"""
from dataclasses import dataclass

from app.models.tenant import Tenant


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int | None = None
    message: str = "rate limit exceeded"


class RateLimiter:
    """Base class. Phase 2: everyone is allowed. Phase 5: Redis token bucket."""

    def allow(self, tenant: Tenant) -> RateLimitResult:
        # NOTE: Phase 5 replaces this with a Redis-backed token bucket keyed on
        # tenant.id / api_key_hash with limits from tenant.rate_limit_plan.
        return RateLimitResult(allowed=True, remaining=None, message="")


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter