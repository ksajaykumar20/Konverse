"""Document ingestion pipeline: parse -> chunk -> embed -> upsert -> mark.

Pure orchestration: reads bytes, extracts, chunks, embeds, writes to Qdrant,
and flips `documents.status` to indexed. It takes an `AsyncSession` so the
Celery worker and tests both drive it — tests pass an in-memory SQLite session.

Runs inside the worker's asyncio loop; never on the API request path.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.document import Document
from app.services import chunking, embeddings, extraction, qdrant, storage

logger = logging.getLogger(__name__)


async def run_ingestion(
    settings: Settings, session: AsyncSession, doc: Document
) -> None:
    """Extract -> chunk -> embed -> upsert -> mark `doc` indexed.

    Raises on any failure; the caller is responsible for marking the document
    failed (the worker does so and records the error).
    """
    data = storage.read_upload(doc.storage_path)
    text = extraction.extract_text(doc.filename, data)

    chunks = chunking.split_text(text)
    if not chunks:
        raise ValueError("No extractable text found in document")

    logger.info("embedding %d chunks for doc=%s", len(chunks), doc.id)
    vectors = await embeddings.embed_texts(settings, chunks)

    await qdrant.ensure_collection(settings)
    await qdrant.upsert_document_vectors(
        settings, str(doc.tenant_id), str(doc.id), chunks, vectors
    )

    doc.status = "indexed"
    doc.chunk_count = len(chunks)
    await session.commit()