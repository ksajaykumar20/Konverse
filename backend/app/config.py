"""Pydantic Settings — the single source of truth for environment config.

Both processes (uvicorn API and Celery worker) import this, so a tenant-level
setting edited here applies everywhere. Later phases add provider keys,
vector sizing, rate-limit plan defaults, etc. to this one class.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ----- App -----
    env: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    # ----- PostgreSQL (SQLAlchemy async engine URL) -----
    database_url: str = (
        "postgresql+asyncpg://konverse:konverse@localhost:5432/konverse"
    )

    # ----- Redis (cache + rate limiting + Celery broker) -----
    redis_url: str = "redis://localhost:6379/0"

    # ----- Qdrant (vector store) -----
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "konverse_chunks"

    # ----- Celery -----
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ----- Providers (used from Phase 3 onward) -----
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ----- Document upload storage (Phase 3) -----
    # Local disk for dev; in production point this at object storage and keep
    # only the key in `documents.storage_path`. No schema change required.
    storage_dir: str = "./storage"

    # ----- Vector sizing / embedding (Phase 3) -----
    embedding_model: str = "text-embedding-3-small"
    embedding_size: int = 1536  # matches text-embedding-3-small

    # ----- LLM / retrieval (Phase 4) -----
    anthropic_model: str = "claude-sonnet-4-6"
    retrieval_top_k: int = 5
    # Cosine similarity below this -> skip the LLM, emit the canned fallback.
    retrieval_min_score: float = 0.60
    llm_max_tokens: int = 1024

    # ----- Caching (Phase 4) -----
    # Per-tenant query-embedding cache TTL (seconds). 24h.
    embedding_cache_ttl: int = 86400

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # pydantic maps DATABASE_URL -> database_url automatically.
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (env read once per process)."""
    return Settings()