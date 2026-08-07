"""Tests for the pluggable embedding backend (Phase 8): TEI vs OpenAI.

We patch the internal `_embed` helper (the only network touchpoint) so these
tests exercise the dispatch + bge query-prefix logic without a live TEI/OpenAI.
"""
import pytest

from app.config import Settings
from app.services import embeddings


@pytest.mark.asyncio
async def test_tei_backend_applies_bge_prefix_to_queries_only(monkeypatch):
    """query=True prefixes with the bge instruction; documents stay plain."""
    captured: dict = {}

    async def fake_embed(client, model, texts):
        captured["texts"] = texts
        return [[0.0] * 4 for _ in texts]

    monkeypatch.setattr("app.services.embeddings._embed", fake_embed)
    settings = Settings(
        embedding_backend="tei",
        tei_url="http://tei.local:8080",
        embedding_model="BAAI/bge-base-en-v1.5",
    )

    await embeddings.embed_texts(settings, ["how do I return an item?"], query=True)
    assert captured["texts"] == [
        embeddings.BGE_QUERY_INSTRUCTION + "how do I return an item?"
    ]

    await embeddings.embed_texts(settings, ["how do I return an item?"], query=False)
    assert captured["texts"] == ["how do I return an item?"]


@pytest.mark.asyncio
async def test_tei_missing_url_raises(monkeypatch):
    """A TEI backend without a configured URL fails fast (never touches _embed)."""
    async def fake_embed(client, model, texts):
        raise AssertionError("should not be reached")

    monkeypatch.setattr("app.services.embeddings._embed", fake_embed)
    settings = Settings(embedding_backend="tei", tei_url="", embedding_model="BAAI/bge-base-en-v1.5")

    with pytest.raises(RuntimeError):
        await embeddings.embed_texts(settings, ["x"])


@pytest.mark.asyncio
async def test_openai_backend_no_bge_prefix_and_requires_key(monkeypatch):
    """OpenAI fallback: non-bge models get no query prefix; a missing key errors."""
    captured: dict = {}

    async def fake_embed(client, model, texts):
        captured["texts"] = texts
        return [[0.0] * 4 for _ in texts]

    monkeypatch.setattr("app.services.embeddings._embed", fake_embed)

    s = Settings(
        embedding_backend="openai",
        openai_api_key="k",
        embedding_model="text-embedding-3-small",
    )
    await embeddings.embed_texts(s, ["hello"], query=True)
    assert captured["texts"] == ["hello"]  # no prefix for non-bge

    s_missing = Settings(embedding_backend="openai", openai_api_key="", embedding_model="text-embedding-3-small")
    with pytest.raises(RuntimeError):
        await embeddings.embed_texts(s_missing, ["hello"])


@pytest.mark.asyncio
async def test_unknown_backend_raises():
    settings = Settings(embedding_backend="bogus", tei_url="http://tei.local:8080")
    with pytest.raises(ValueError):
        await embeddings.embed_texts(settings, ["x"])
