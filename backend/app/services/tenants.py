"""Shared tenant operations — the single implementation used by the public
self-serve router AND the platform-admin router, so the two never drift.

Covers create (key-once), update, API-key regeneration, usage aggregation, and
the guarded hard delete (Qdrant + storage + DB row; child rows cascade).
"""
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.chat import ChatSession, Message
from app.models.document import Document
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate
from app.services import qdrant, storage
from app.services.auth import generate_api_key, hash_api_key


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "tenant"


async def _unique_slug(db: AsyncSession, slug: str) -> str:
    candidate = slug
    if not await db.scalar(select(Tenant.id).where(Tenant.slug == candidate)):
        return candidate
    return f"{slug}-{uuid.uuid4().hex[:8]}"


async def create_tenant(db: AsyncSession, payload: TenantCreate) -> tuple[Tenant, str]:
    """Create a tenant; returns (tenant, plaintext_key). Key is shown exactly once."""
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
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(tenant)
    return tenant, key


async def update_tenant(
    db: AsyncSession, tenant: Tenant, payload: TenantUpdate
) -> None:
    """Apply the set fields from an update payload to a tenant row."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    await db.commit()


async def regenerate_api_key(db: AsyncSession, tenant: Tenant) -> str:
    """Rotate a tenant's API key. The old key stops working immediately;
    the new key is returned exactly once."""
    key = generate_api_key()
    tenant.api_key_hash = hash_api_key(key)
    await db.commit()
    return key


async def tenant_usage(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
    """Aggregate a tenant's usage counts + last activity (for the admin table)."""
    doc_count = await db.scalar(
        select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
    )
    session_count = await db.scalar(
        select(func.count())
        .select_from(ChatSession)
        .where(ChatSession.tenant_id == tenant_id)
    )
    message_count = await db.scalar(
        select(func.count()).select_from(Message).where(Message.tenant_id == tenant_id)
    )
    last_active = await db.scalar(
        select(func.max(Message.created_at)).where(Message.tenant_id == tenant_id)
    )
    return {
        "document_count": int(doc_count or 0),
        "session_count": int(session_count or 0),
        "message_count": int(message_count or 0),
        "last_active": last_active,
    }


async def hard_delete_tenant(
    settings: Settings, db: AsyncSession, tenant: Tenant
) -> None:
    """Irreversibly remove a tenant: Qdrant vectors, storage files, then the DB
    row (child documents/sessions/messages cascade via FK). Disable instead via
    `update_tenant(is_active=False)` to keep data reversible."""
    # Collect storage paths BEFORE deleting the row (we need the rows to exist).
    doc_paths = list(
        await db.scalars(
            select(Document.storage_path).where(Document.tenant_id == tenant.id)
        )
    )
    await qdrant.delete_tenant_points(settings, str(tenant.id))
    for rel in doc_paths:
        storage.delete_document(rel)
    await db.delete(tenant)
    await db.commit()