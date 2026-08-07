"""Tests for the Phase 4 chat/RAG path (retrieval + Qdrant mocked)."""
import json

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.services.retrieval import RetrievalResult

API_KEY = "X-API-Key"


async def _create_tenant(client: AsyncClient, name: str) -> dict:
    r = await client.post("/api/tenants", json={"name": name, "industry": "test"})
    assert r.status_code == 201, r.text
    return r.json()


def _settings() -> Settings:
    return Settings(
        openai_api_key="k",
        anthropic_api_key="ak",
        qdrant_url="http://localhost:9999",
        redis_url="redis://localhost:9999/0",
        embedding_size=4,
    )


def _events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out


# --- retrieved context grounds & streams, then logs -------------------------


@pytest.mark.asyncio
async def test_grounded_chat_streams_and_logs(client, monkeypatch):
    t = await _create_tenant(client, "Shop")

    async def fake_retrieve(settings, tenant_id, query):
        return RetrievalResult(
            chunks=[{"text": "Only an Acme branded answer here.", "score": 0.9}],
            max_score=0.9,
        )

    async def fake_stream(settings, system_prompt, user_message):
        yield "Hello "
        yield "world"

    monkeypatch.setattr("app.services.retrieval.retrieve", fake_retrieve)
    monkeypatch.setattr("app.services.llm.stream_answer", fake_stream)

    resp = await client.post(
        f"/api/chat/{t['id']}",
        headers={API_KEY: t["api_key"]},
        json={"message": "What do you sell?"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    events = _events(resp.text)
    done = next(e for e in events if e["type"] == "done")
    assert done["was_answered"] is True
    assert "world" in done["text"]

    # history shows user + assistant, assistant marked answered
    sid = next(e for e in events if e["type"] == "session")["session_id"]
    hist = await client.get(
        f"/api/chat/{t['id']}/history/{sid}", headers={API_KEY: t["api_key"]}
    )
    assert hist.status_code == 200
    msgs = hist.json()["messages"]
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["was_answered"] is True


# --- low confidence: skip LLM, emit fallback, log as unanswered ------------


@pytest.mark.asyncio
async def test_low_confidence_fallback_skips_llm(client, monkeypatch):
    t = await _create_tenant(client, "LowCo")

    async def fake_retrieve(settings, tenant_id, query):
        return RetrievalResult(
            chunks=[{"text": "unrelated", "score": 0.2}], max_score=0.2
        )

    called = {"n": 0}

    async def boom_stream(settings, system_prompt, user_message):
        called["n"] += 1
        yield "should not happen"

    monkeypatch.setattr("app.services.retrieval.retrieve", fake_retrieve)
    monkeypatch.setattr("app.services.llm.stream_answer", boom_stream)

    resp = await client.post(
        f"/api/chat/{t['id']}",
        headers={API_KEY: t["api_key"]},
        json={"message": "something unknown"},
    )
    assert resp.status_code == 200
    events = _events(resp.text)
    done = next(e for e in events if e["type"] == "done")
    assert done["was_answered"] is False
    assert called["n"] == 0  # LLM never invoked


# --- retrieval isolation: tenant_id always scoped into the Qdrant filter ----


@pytest.mark.asyncio
async def test_retrieval_scopes_by_tenant():
    settings = _settings()

    seen = []

    async def fake_embed(settings, tenant_id, query):
        return [0.1, 0.2, 0.3, 0.4]

    async def fake_search(settings, tenant_id, query_vector):
        seen.append(tenant_id)
        return [
            type("P", (), {"payload": {"text": "x", "document_id": "d"}, "score": 0.9})()
        ]

    import app.services.retrieval as ret

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(ret, "_embed_query", fake_embed)
    monkeypatch.setattr(ret, "_search_qdrant", fake_search)

    await ret.retrieve(settings, "tenant-aaa", "hello")
    await ret.retrieve(settings, "tenant-bbb", "hello")
    assert seen == ["tenant-aaa", "tenant-bbb"]


def test_retrieval_result_fields():
    r = RetrievalResult(chunks=[{"text": "a", "score": 0.8}], max_score=0.8)
    assert r.max_score == 0.8
    assert r.chunks[0]["text"] == "a"