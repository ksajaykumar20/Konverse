"""Document request/response schemas for the ingestion endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    status: str  # processing | indexed | failed
    chunk_count: int
    error_message: str | None
    created_at: datetime


class IngestResponse(BaseModel):
    """Returned to the caller of POST /ingest immediately (async enqueue)."""

    id: uuid.UUID
    filename: str
    status: str
    message: str