"""Document ingestion endpoints.

POST  /ingest/{tenant_id}     — upload -> save -> enqueue -> return (async)
GET   /documents/{tenant_id}  — list docs + status for dashboard polling

Both are auth-locked to the tenant that owns the path tenant_id (404 for any
foreign tenant, matching the Phase 2 isolation rule).
"""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import AsyncSessionLocal, get_db
from app.models.document import Document
from app.models.tenant import Tenant
from app.schemas.document import DocumentRead, IngestResponse
from app.services import storage
from app.services.auth import require_api_key
from app.worker.tasks import ingest_document as ingest_task
from app.worker.tasks import run_worker_ingestion

router = APIRouter(tags=["ingest"])


def _require_owner(tenant_id: uuid.UUID, current: Tenant) -> None:
    # Same 404-for-all-misses rule as tenants.py: no existence leak.
    if current.id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")


@router.post(
    "/ingest/{tenant_id}",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_document(
    tenant_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: Tenant = Depends(require_api_key),
) -> IngestResponse:
    _require_owner(tenant_id, current)

    data = await file.read()
    # Persist to disk (returns a safe relative path) BEFORE enqueuing so the
    # worker has the bytes available even if it picks the job 'processing'.
    rel_path = storage.save_upload(data, file.filename or "upload.bin")

    doc = Document(
        tenant_id=current.id,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "",
        storage_path=rel_path,
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    if get_settings().celery_task_always_eager:
        # Local (no-Docker, no-Redis) profile: run ingestion in a background
        # task in this process rather than handing it to a broker+worker. We
        # spawn a fresh session (like the Celery task does) and let it flip the
        # document to "indexed" asynchronously — the dashboard polls until then.
        async def _ingest_in_process(document_id: str) -> None:
            async with AsyncSessionLocal() as session:
                await run_worker_ingestion(session, document_id)

        asyncio.create_task(_ingest_in_process(str(doc.id)))
    else:
        # Production: enqueue async ingestion. A Redis broker must be reachable;
        # the worker (independently scalable) does the heavy lifting off-path.
        ingest_task.delay(str(doc.id))

    return IngestResponse(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        message="document uploaded; ingestion queued",
    )


@router.get("/documents/{tenant_id}", response_model=list[DocumentRead])
async def list_documents(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: Tenant = Depends(require_api_key),
) -> list[Document]:
    _require_owner(tenant_id, current)
    result = await db.scalars(
        select(Document)
        .where(Document.tenant_id == current.id)
        .order_by(Document.created_at.desc())
    )
    return list(result)