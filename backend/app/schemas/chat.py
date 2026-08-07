"""Chat request / history schemas (the response is streamed over SSE)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = Field(default=None)
    message: str = Field(min_length=1, max_length=8000)


class HistoryMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    was_answered: bool | None = None
    confidence: float | None = None
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    session_id: uuid.UUID
    messages: list[HistoryMessage]