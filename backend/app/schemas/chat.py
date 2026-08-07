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
    guardrail_category: str | None = None
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    session_id: uuid.UUID
    messages: list[HistoryMessage]


class SessionSummary(BaseModel):
    """One chat session row for the dashboard's Sessions screen."""

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class ChatSessionsResponse(BaseModel):
    sessions: list[SessionSummary]