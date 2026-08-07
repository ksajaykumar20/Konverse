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

    # ----- Vector sizing (Phase 3) -----
    embedding_size: int = 1536  # OpenAI text-embedding-3-small

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