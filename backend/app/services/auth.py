"""Tenant authentication via a bearer API key.

Every tenant holds a long random key (`kv_...`) presented in the `X-API-Key`
header. We store only a sha256 hash, so a DB leak yields no usable key.

Auth is self-contained (stateless): any API replica can validate a key by a
single hashed lookup, so the authentication layer scales horizontally with the
API itself. The rate-limit hook is called here so it's enforced on every
protected tenant route from Phase 2 on.
"""
import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.tenant import Tenant
from app.services.ratelimit import get_rate_limiter

API_KEY_HEADER = "X-API-Key"


def generate_api_key() -> str:
    """Return a fresh tenant API key. Shown to the caller exactly once."""
    return "sk_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """sha256 hash of a key — the only thing we persist."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def _lookup_tenant(db: AsyncSession, token: str) -> Tenant | None:
    return await db.scalar(
        select(Tenant).where(Tenant.api_key_hash == hash_api_key(token))
    )


def _deny(detail: str, code: int = status.HTTP_401_UNAUTHORIZED) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


async def require_api_key(
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(None, alias=API_KEY_HEADER),
) -> Tenant:
    """Dependency: authenticate the X-API-Key header and return its tenant."""
    if not x_api_key:
        raise _deny("Missing API key. Provide it in the X-API-Key header.")

    tenant = await _lookup_tenant(db, x_api_key)
    if tenant is None:
        raise _deny("Invalid API key.")

    if not tenant.is_active:
        raise _deny("This tenant is disabled.", status.HTTP_403_FORBIDDEN)

    # Rate-limit hook (Phase 5): Redis sliding-window log per API key.
    result = await get_rate_limiter().allow(tenant)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.message or "Rate limit exceeded.",
            headers=(
                {"Retry-After": str(result.retry_after)}
                if result.retry_after
                else None
            ),
        )

    return tenant


async def require_admin(
    x_admin_key: str = Header(None, alias="X-Admin-Key"),
) -> bool:
    """Dependency: authenticate the platform operator via the X-Admin-Key header.

    Compares against `ADMIN_API_KEY` in constant time. When the key is unset the
    admin API is disabled (503) so an unconfigured deployment never exposes a
    wide-open console. Admin ops are intentionally not rate-limited — the
    operator is a single, trusted actor.
    """
    settings = get_settings()
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured (set ADMIN_API_KEY).",
        )
    if not x_admin_key or not secrets.compare_digest(
        x_admin_key, settings.admin_api_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key."
        )
    return True