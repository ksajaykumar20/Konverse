"""Tests for the Docker-free local stack (Phase 9).

These cover the no-key, no-container units added for the fully-local profile:
local (fastembed) embedding dispatch, local extractive LLM, the local Qdrant
client routing, and Celery-eager ingestion so the whole loop runs in-process.

They use stripped-down fakes where a real model network download would otherwise
pause the suite — the dispatch logic is what we assert, not the model weights.
"""
import math

import pytest

from app.config import Settings
from app.services import embeddings, llm, qdrant


def _local_settings(qdrant_url: str = ":memory:") -> Settings:
    return Settings(
        embedding_backend="local",
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_size=384,
        qdrant_url=qdrant_url,
        llm_backend="local",
    )


# --- local embedding dispatch ------------------------------------------------


@pytest.mark.asyncio
async def test_local_backend_fails_fast_without_model(monkeypatch):
    """A local model not yet downloaded should raise a clear error quickly,
    rather than silently falling through to a remote backend."""
    s = _local_settings()

    # Monkeypatch _get_local_embedder so we don't download/run an ONNX model in
    # a unit test. Instead assert the dispatch reaches the local branch.
    async def fake_getter(_settings):
        raise RuntimeError("model download needed on first use")

    monkeypatch.setattr(embeddings, "_get_local_embedder", fake_getter)
    with pytest.raises(RuntimeError):
        await embeddings.embed_texts(s, ["hello"])


@pytest.mark.asyncio
async def test_embed_dispatch_unknown_backend_raises():
    s = Settings(embedding_backend="bogus")
    with pytest.raises(ValueError):
        await embeddings.embed_texts(s, ["x"])


# --- local LLM (extractive, citing) ------------------------------------------


@pytest.mark.asyncio
async def test_local_llm_cites_top_chunk():
    s = _local_settings()
    chunks = [
        {"text": "Acme ships within 24 hours.", "score": 0.9},
        {"text": "Returns accepted for 30 days.", "score": 0.7},
    ]
    out = [d async for d in llm.stream_answer(s, "sys", "shipping", chunks=chunks)]
    text = "".join(out)
    assert "Acme ships within 24 hours" in text  # top chunk cited verbatim


@pytest.mark.asyncio
async def test_local_llm_empty_chunks_fallback():
    s = _local_settings()
    out = [d async for d in llm.stream_answer(s, "sys", "q", chunks=[])]
    assert "don't have enough information" in "".join(out)


@pytest.mark.asyncio
async def test_anthropic_backend_requires_key():
    s = Settings(llm_backend="anthropic", anthropic_api_key="")
    with pytest.raises(RuntimeError):
        async for _ in llm.stream_answer(s, "sys", "q", chunks=[]):
            pass


# --- local Qdrant client routing ---------------------------------------------


def test_client_routes_inmemory_to_shared_singleton():
    s = _local_settings(qdrant_url=":memory:")
    c1 = qdrant._client(s)
    c2 = qdrant._client(s)
    assert c1 is c2  # shared: points survive across per-call opens


def test_client_uses_local_path_for_disk_mode(tmp_path):
    # A path under the pytest temp dir so the test never litters the repo.
    s = _local_settings(qdrant_url=str(tmp_path / "qdrant"))
    client = qdrant._client(s)
    assert isinstance(client, qdrant.AsyncQdrantClient)
    # Installed qdrant-client maps a filesystem path to a LOCAL (in-process)
    # store via the `path=` kwarg, not an HTTP remote.
    assert type(client._client).__name__ == "AsyncQdrantLocal"


# --- Celery eager ingestion (no broker) --------------------------------------

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from app.db import base as db_base
from app.models.document import Document
from app.models.tenant import Tenant
from app.services import storage as storage_mod
import app.models  # noqa: F401


@pytest.mark.asyncio
async def test_eager_ingestion_runs_in_process(monkeypatch):
    """With CELERY_TASK_ALWAYS_EAGER, ingestion should complete in-process:
    no broker is touched and the document flips to `indexed`."""
    from app.worker.tasks import run_worker_ingestion

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(db_base.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    s = _local_settings()

    # Fake the heavy pieces so the in-process pipeline runs fast and offline.
    monkeypatch.setattr(
        storage_mod, "read_upload", lambda path: b"Acme policy text here."
    )
    monkeypatch.setattr(
        "app.services.ingestion.extraction.extract_text",
        lambda filename, data: "Acme policy text here.",
    )
    async def fake_embed(_settings, texts, **kw):
        return [[0.1] * 384 for _ in texts]

    monkeypatch.setattr(
        "app.services.ingestion.embeddings.embed_texts", fake_embed
    )

    upserted = {}

    async def fake_ensure(_s):
        pass

    async def fake_upsert(_s, tenant_id, document_id, texts, vectors):
        upserted["document_id"] = document_id

    monkeypatch.setattr("app.services.qdrant.ensure_collection", fake_ensure)
    monkeypatch.setattr("app.services.qdrant.upsert_document_vectors", fake_upsert)
    # ensure_collection is called via app.services.ingestion.qdrant reference;
    # we patched the function on the module so both resolve to the fake above.

    async with factory() as session:
        tenant = Tenant(
            name="LocalCo", slug="localco", api_key_hash="abc", is_active=True
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)

        doc = Document(
            tenant_id=tenant.id,
            filename="policy.txt",
            content_type="text/plain",
            storage_path="rel",
            status="processing",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = str(doc.id)

        await run_worker_ingestion(session, doc_id)

        await session.refresh(doc)
        assert doc.status == "indexed"
        assert doc.chunk_count == 1

    assert upserted.get("document_id") == doc_id
    await engine.dispose()