"""Tests for the Phase 3 ingestion pipeline (SQLite + mocked external calls)."""
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.models.document import Document
from app.services import storage as storage_mod
from app.services.ingestion import run_ingestion
from app.worker.tasks import run_worker_ingestion

API_KEY = "X-API-Key"


def _settings(tmp_path) -> Settings:
    return Settings(
        storage_dir=str(tmp_path),
        openai_api_key="test-key",
        qdrant_url="http://localhost:9999",
        embedding_size=4,
    )


async def _create_tenant(client: AsyncClient) -> dict:
    r = await client.post("/api/tenants", json={"name": "IngestCo"})
    assert r.status_code == 201, r.text
    return r.json()


# --- endpoint: upload -> 202, doc 'processing', enqueued -------------------


@pytest.mark.asyncio
async def test_ingest_upload_enqueues_and_lists(client, monkeypatch):
    t = await _create_tenant(client)

    # The router reads the GLOBAL get_settings() for the eager flag. Pin it OFF
    # here so this test asserts the broker/Celery path regardless of any local
    # `.env` that sets CELERY_TASK_ALWAYS_EAGER=true.
    monkeypatch.setattr(
        "app.routers.ingest.get_settings",
        lambda: Settings(celery_task_always_eager=False),
    )

    calls: list[str] = []
    monkeypatch.setattr(
        "app.routers.ingest.ingest_task",
        SimpleNamespace(delay=lambda doc_id: calls.append(doc_id)),
    )
    # No real disk write in the router test.
    monkeypatch.setattr(storage_mod, "save_upload", lambda data, name: "rel-path.bin")

    resp = await client.post(
        f"/api/ingest/{t['id']}",
        headers={API_KEY: t["api_key"]},
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "processing"
    assert len(calls) == 1  # exactly one Celery job enqueued

    listing = await client.get(
        f"/api/documents/{t['id']}", headers={API_KEY: t["api_key"]}
    )
    assert listing.status_code == 200
    docs = listing.json()
    assert len(docs) == 1
    assert docs[0]["status"] == "processing"


@pytest.mark.asyncio
async def test_ingest_rejects_foreign_tenant(client):
    a = await _create_tenant(client)
    b = await _create_tenant(client)
    resp = await client.post(
        f"/api/ingest/{a['id']}",
        headers={API_KEY: b["api_key"]},
        files={"file": ("x.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 404


# --- worker: run_ingestion marks indexed on success ------------------------


@pytest.mark.asyncio
async def test_run_ingestion_indexes_document(client, monkeypatch, tmp_path):
    t = await _create_tenant(client)
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        storage_mod, "read_upload", lambda rel: b"Acme Grocery sells apples. Refunds within 30 days."
    )
    async def _fake_embed(settings, texts):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    async def _fake_ensure(settings):
        return None

    async def _fake_upsert(settings, tenant_id, doc_id, texts, vectors):
        return None

    monkeypatch.setattr("app.services.embeddings.embed_texts", _fake_embed)
    monkeypatch.setattr("app.services.qdrant.ensure_collection", _fake_ensure)
    monkeypatch.setattr("app.services.qdrant.upsert_document_vectors", _fake_upsert)

    async with client._factory() as session:
        doc = Document(
            tenant_id=uuid.UUID(t["id"]),
            filename="notes.txt",
            content_type="text/plain",
            storage_path="x",
            status="processing",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        await run_ingestion(settings, session, doc)
        assert doc.status == "indexed"
        assert doc.chunk_count > 0

        await session.refresh(doc)  # confirm committed
        assert doc.status == "indexed"


# --- worker: failure marks document failed --------------------------------


@pytest.mark.asyncio
async def test_worker_marks_document_failed(client):
    t = await _create_tenant(client)
    async with client._factory() as session:
        doc = Document(
            tenant_id=uuid.UUID(t["id"]),
            filename="missing.bin",
            content_type="application/octet-stream",
            storage_path="does-not-exist.bin",  # read_upload will fail
            status="processing",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id

        with pytest.raises(Exception):
            await run_worker_ingestion(session, str(doc_id))

        await session.refresh(doc)
        assert doc.status == "failed"
        assert doc.error_message