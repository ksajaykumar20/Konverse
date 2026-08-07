"""Tenant management endpoints.

POST /tenants            — public, returns the api_key exactly once
GET  /tenants/me         — current tenant (from X-API-Key)
GET  /tenants/{id}       — auth-locked; only the owner reads its own tenant
PATCH /tenants/{id}      — auth-locked; owner updates its own tenant
"""
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import (
    TenantCreate,
    TenantCreateResponse,
    TenantRead,
    TenantUpdate,
)
from app.services.auth import generate_api_key, hash_api_key, require_api_key

router = APIRouter(prefix="/tenants", tags=["tenants"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "tenant"


async def _unique_slug(db: AsyncSession, slug: str) -> str:
    """Return `slug` guaranteed unique in the table."""
    candidate = slug
    if not await db.scalar(select(Tenant.id).where(Tenant.slug == candidate)):
        return candidate
    return f"{slug}-{uuid.uuid4().hex[:8]}"


async def _get_owned_tenant(
    tenant_id: uuid.UUID, current: Tenant, db: AsyncSession
) -> Tenant:
    """Fetch a tenant by id but only if it belongs to the authenticated tenant.

    Returns 404 for any miss — including a real one owned by someone else — so
    cross-tenant reads don't leak whether a tenant exists.
    """
    if current.id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    # It's the current tenant; we already loaded it via the API key.
    return current


@router.post("", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate, db: AsyncSession = Depends(get_db)
) -> TenantCreateResponse:
    slug = await _unique_slug(db, payload.slug or _slugify(payload.name))

    key = generate_api_key()
    tenant = Tenant(
        name=payload.name,
        slug=slug,
        industry=payload.industry,
        api_key_hash=hash_api_key(key),
        system_prompt=payload.system_prompt or "",
        rate_limit_plan=payload.rate_limit_plan or "free",
    )
    db.add(tenant)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Could not create tenant"
        ) from None
    await db.refresh(tenant)

    return TenantCreateResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        industry=tenant.industry,
        api_key=key,
        rate_limit_plan=tenant.rate_limit_plan,
        is_active=tenant.is_active,
        created_at=tenant.created_at,
    )


@router.get("/me", response_model=TenantRead)
async def get_my_tenant(current: Tenant = Depends(require_api_key)) -> Tenant:
    return current


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: Tenant = Depends(require_api_key),
) -> Tenant:
    return await _get_owned_tenant(tenant_id, current, db)


@router.patch("/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current: Tenant = Depends(require_api_key),
) -> Tenant:
    await _get_owned_tenant(tenant_id, current, db)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(current, field, value)

    await db.commit()
    await db.refresh(current)
    return current