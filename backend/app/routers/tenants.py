"""Tenant management endpoints (public, self-serve + peer operations).

POST /tenants            — public, returns the api_key exactly once
GET  /tenants/me         — current tenant (from X-API-Key)
GET  /tenants/{id}       — auth-locked; only the owner reads its own tenant
PATCH /tenants/{id}      — auth-locked; owner updates its own tenant

Platform-wide list/detail/delete/regenerate live in the admin router
(/api/admin) and share the same tenant service as this router.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantCreateResponse, TenantRead, TenantUpdate
from app.services.auth import require_api_key
from app.services import tenants as tenant_svc

router = APIRouter(prefix="/tenants", tags=["tenants"])


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
    tenant, key = await tenant_svc.create_tenant(db, payload)
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
    await tenant_svc.update_tenant(db, current, payload)
    await db.refresh(current)
    return current