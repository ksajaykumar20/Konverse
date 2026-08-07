"""Platform-admin endpoints — manage ALL tenants.

Auth: X-Admin-Key must equal ADMIN_API_KEY (constant-time compare in
`require_admin`). When the key is unset the router returns 503 (disabled).

Surface, all under /api/admin and admin-authenticated:
  GET    /tenants                      list all + usage counts (search/filter/paged)
  POST   /tenants                      onboard a tenant (key-once)
  GET    /tenants/{id}                 detail + usage
  PATCH  /tenants/{id}                 update profile/plan/guardrails/is_active
  POST   /tenants/{id}/regenerate-key  rotate API key (key-once)
  DELETE /tenants/{id}?confirm=hard    irreversible purge (Qdrant+storage+row)
  GET    /tenants/{id}/documents       drill-in
  GET    /tenants/{id}/sessions        drill-in
  GET    /tenants/{id}/sessions/{sid}  session transcript

Disabling is a safe PATCH is_active=false (reversible); hard delete needs the
explicit `?confirm=hard` flag so a disable action can't destroy data by accident.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.chat import ChatSession, Message
from app.models.document import Document
from app.models.tenant import Tenant
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatSessionsResponse,
    HistoryMessage,
    SessionSummary,
)
from app.schemas.document import DocumentRead
from app.schemas.tenant import TenantCreate, TenantCreateResponse, TenantUpdate
from app.services import tenants as tenant_svc
from app.services.auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


async def _get_tenant_or_404(db: AsyncSession, tenant_id) -> Tenant:
    tenant = await db.get(Tenant, uuid.UUID(str(tenant_id)))
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


async def _with_usage(db: AsyncSession, tenant: Tenant) -> dict:
    """Serialize a tenant together with its usage counts for the admin table."""
    usage = await tenant_svc.tenant_usage(db, tenant.id)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "industry": tenant.industry,
        "rate_limit_plan": tenant.rate_limit_plan,
        "is_active": tenant.is_active,
        "system_prompt": tenant.system_prompt,
        "guardrail_rules": tenant.guardrail_rules,
        "created_at": tenant.created_at,
        "updated_at": tenant.updated_at,
        **usage,
    }


@router.get("/verify")
async def admin_verify(_admin: bool = Depends(require_admin)):
    """Key-only check — no DB touch. Lets the dashboard validate the admin key
    (and stay logged in) even when the data layer is down."""
    return {"admin": True}


@router.get("/tenants")
async def admin_list_tenants(
    q: str | None = None,
    status_: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    stmt = select(Tenant).order_by(Tenant.created_at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Tenant.name.ilike(like) | Tenant.slug.ilike(like))
    if status_ == "active":
        stmt = stmt.where(Tenant.is_active.is_(True))
    elif status_ == "disabled":
        stmt = stmt.where(Tenant.is_active.is_(False))
    elif status_:
        raise HTTPException(400, "status must be 'active' or 'disabled'")

    rows = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    return {"tenants": [await _with_usage(db, t) for t in rows]}


@router.post("/tenants", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_tenant(
    payload: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
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


@router.get("/tenants/{tenant_id}")
async def admin_get_tenant(
    tenant_id,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    return await _with_usage(db, await _get_tenant_or_404(db, tenant_id))


@router.patch("/tenants/{tenant_id}")
async def admin_update_tenant(
    tenant_id,
    payload: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    await tenant_svc.update_tenant(db, tenant, payload)
    await db.refresh(tenant)
    return await _with_usage(db, tenant)


@router.post("/tenants/{tenant_id}/regenerate-key")
async def admin_regenerate_key(
    tenant_id,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    key = await tenant_svc.regenerate_api_key(db, tenant)
    return {"id": tenant.id, "api_key": key}


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_tenant(
    tenant_id,
    confirm: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    if confirm != "hard":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Hard delete requires ?confirm=hard. To keep the tenant's data "
            "reversible, PATCH is_active=false instead.",
        )
    tenant = await _get_tenant_or_404(db, tenant_id)
    await tenant_svc.hard_delete_tenant(get_settings(), db, tenant)


@router.get("/tenants/{tenant_id}/documents", response_model=list[DocumentRead])
async def admin_list_documents(
    tenant_id,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    rows = await db.scalars(
        select(Document)
        .where(Document.tenant_id == tenant.id)
        .order_by(Document.created_at.desc())
    )
    return list(rows)


@router.get("/tenants/{tenant_id}/sessions", response_model=ChatSessionsResponse)
async def admin_list_sessions(
    tenant_id,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    tenant = await _get_tenant_or_404(db, tenant_id)
    rows = await db.execute(
        select(
            ChatSession.id,
            ChatSession.title,
            ChatSession.created_at,
            ChatSession.updated_at,
        )
        .where(ChatSession.tenant_id == tenant.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(200)
    )
    sessions = []
    for session_id, title, created_at, updated_at in rows:
        count = await db.scalar(
            select(func.count()).select_from(Message).where(Message.session_id == session_id)
        )
        sessions.append(
            SessionSummary(
                id=session_id,
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                message_count=int(count or 0),
            )
        )
    return ChatSessionsResponse(sessions=sessions)


@router.get("/tenants/{tenant_id}/sessions/{session_id}", response_model=ChatHistoryResponse)
async def admin_get_session(
    tenant_id,
    session_id,
    db: AsyncSession = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    session = await db.get(ChatSession, uuid.UUID(str(session_id)))
    if session is None or str(session.tenant_id) != str(tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    rows = await db.scalars(
        select(Message).where(Message.session_id == session.id).order_by(Message.created_at)
    )
    return ChatHistoryResponse(
        session_id=session.id,
        messages=[HistoryMessage.model_validate(m) for m in rows],
    )