"""Celery task definitions.

Phase 3 adds `ingest_document`, the async ingestion job. It runs its own
asyncio loop (the prefork worker has none by default) so the async engine,
OpenAI client, and Qdrant client all bind to that loop for the task's lifetime.
"""
import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.services.ingestion import run_ingestion
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="workers.add")
def add(x: int, y: int) -> int:
    """Phase 1 smoke test: proves the worker consumes jobs from the broker."""
    return x + y


async def run_worker_ingestion(
    session: AsyncSession, document_id: str
) -> None:
    """Run ingestion for `document_id` in a given session.

    Kept separate from the Celery task so tests can drive it with an in-memory
    SQLite session (and so the failure-marking path is unit-testable).
    """
    settings = get_settings()
    # Celery hands us the id as a string; coerce to UUID so the Uuid PK lookup
    # binds correctly on both Postgres and SQLite.
    doc = await session.get(Document, uuid.UUID(str(document_id)))
    if doc is None:
        logger.warning("ingest_document: doc %s not found", document_id)
        return
    try:
        await run_ingestion(settings, session, doc)
    except Exception as exc:  # noqa: BLE001 — record any failure
        doc.status = "failed"
        doc.error_message = str(exc)
        await session.commit()
        logger.error("ingest_document failed for %s: %s", document_id, exc)
        raise


@celery_app.task(name="workers.ingest_document")
def ingest_document(document_id: str) -> None:
    """Enqueue-friendly wrapper: parses/chunks/embeds/upserts one document.

    Runs its own asyncio loop (the prefork worker has none by default) so the
    async engine, OpenAI client, and Qdrant client bind to it fresh per task.
    On failure the document is marked `failed` and the task re-raises for
    Celery's monitoring.
    """

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            await run_worker_ingestion(session, document_id)

    return asyncio.run(_run())