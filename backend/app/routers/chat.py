"""Chat endpoints — RAG-grounded streaming over Server-Sent Events.

POST /chat/{tenant_id}                       -> SSE stream (tokens)
GET  /chat/{tenant_id}/history/{session_id}  -> session transcript

Both are auth-locked to the tenant that owns the path (404 for foreign
tenants). The response streams via SSE so consumers (dashboard, Phase 7
widget) render token-by-token; no WebSocket state held across replicas.
"""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.tenant import Tenant
from app.models.chat import ChatSession, Message
from app.schemas.chat import ChatHistoryResponse, ChatRequest, HistoryMessage
from app.services import llm, prompt, retrieval
from app.services.auth import require_api_key

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _require_owner(tenant_id: uuid.UUID, current: Tenant) -> None:
    if current.id != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tenant not found")


async def _get_or_create_session(
    db: AsyncSession, tenant: Tenant, body: ChatRequest
) -> ChatSession:
    if body.session_id:
        session = await db.get(ChatSession, uuid.UUID(str(body.session_id)))
        if session is None or session.tenant_id != tenant.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session
    session = ChatSession(tenant_id=tenant.id, title=body.message[:80])
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def _log_message(
    db: AsyncSession, session: ChatSession, tenant: Tenant, *, role: str,
    content: str, was_answered: bool | None = None, confidence: float | None = None,
) -> None:
    db.add(
        Message(
            session_id=session.id, tenant_id=tenant.id, role=role, content=content,
            was_answered=was_answered, confidence=confidence,
        )
    )
    await db.commit()


@router.post("/{tenant_id}")
async def chat(
    tenant_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current: Tenant = Depends(require_api_key),
) -> StreamingResponse:
    _require_owner(tenant_id, current)
    settings = get_settings()

    session = await _get_or_create_session(db, current, body)
    await _log_message(db, session, current, role="user", content=body.message)

    # Retrieve BEFORE streaming so the low-confidence branch can skip the LLM
    # for the whole session and log one message.
    result = await retrieval.retrieve(settings, str(current.id), body.message)
    low_conf = result.max_score < settings.retrieval_min_score

    async def _persist_answer(content: str, was_answered: bool) -> None:
        await _log_message(
            db, session, current, role="assistant", content=content,
            was_answered=was_answered, confidence=result.max_score,
        )

    async def _stream() -> str:
        if low_conf:
            answer = prompt.fallback_text()
            yield _sse({"type": "session", "session_id": str(session.id)})
            yield _sse({"type": "token", "text": answer})
            yield _sse({"type": "done", "text": answer, "was_answered": False})
            await _persist_answer(answer, was_answered=False)
            return

        system_prompt = prompt.build_system_prompt(
            current.name, current.system_prompt,
            prompt.render_context(result.chunks),
        )
        parts: list[str] = []
        yield _sse({"type": "session", "session_id": str(session.id)})
        async for delta in llm.stream_answer(settings, system_prompt, body.message):
            parts.append(delta)
            yield _sse({"type": "token", "text": delta})
        answer = "".join(parts)
        yield _sse({"type": "done", "text": answer, "was_answered": True})
        await _persist_answer(answer, was_answered=True)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.get("/{tenant_id}/history/{session_id}", response_model=ChatHistoryResponse)
async def chat_history(
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: Tenant = Depends(require_api_key),
) -> ChatHistoryResponse:
    _require_owner(tenant_id, current)
    session = await db.get(ChatSession, uuid.UUID(str(session_id)))
    if session is None or session.tenant_id != current.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    rows = await db.scalars(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.created_at)
    )
    return ChatHistoryResponse(
        session_id=session.id,
        messages=[HistoryMessage.model_validate(m) for m in rows],
    )