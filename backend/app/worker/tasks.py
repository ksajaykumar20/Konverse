"""Celery task definitions.

Phase 1 ships one dummy task so we can prove the worker boots, connects to the
Redis broker, and picks up jobs. Phase 3 replaces `add` with the real
`ingest_document` flow (parse -> chunk -> embed -> Qdrant upsert -> update
documents.status).
"""
from app.worker.celery_app import celery_app


@celery_app.task(name="workers.add")
def add(x: int, y: int) -> int:
    """Smoke-test task: `add.delay(2, 3)` -> result 5."""
    return x + y