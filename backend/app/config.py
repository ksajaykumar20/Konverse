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

    # ----- Vector sizing / embedding (Phase 3; backend pluggable from Phase 8) -----
    # Backend: "tei" (default — an OpenAI-compatible TEI/HF endpoint) or
    # "openai" (fallback). The model string is the model the backend serves;
    # embedding_size must match that model's output dimension (Qdrant collection
    # dimension is fixed at creation, so changing model usually means a new
    # collection + re-ingest — see README).
    embedding_backend: str = "tei"
    tei_url: str = "http://localhost:8080"  # TEI / OpenAI-compatible endpoint
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_size: int = 768  # matches bge-base-en-v1.5 (768-d)

    # ----- LLM / retrieval (Phase 4) -----
    anthropic_model: str = "claude-sonnet-4-6"
    retrieval_top_k: int = 5
    # Cosine similarity below this -> skip the LLM, emit the canned fallback.
    retrieval_min_score: float = 0.60
    llm_max_tokens: int = 1024

    # ----- Caching (Phase 4) -----
    # Per-tenant query-embedding cache TTL (seconds). 24h.
    embedding_cache_ttl: int = 86400

    # ----- Rate limiting (Phase 5) -----
    # Sliding-window limits per plan: "plan=requests/window_seconds", comma-sep.
    # e.g. free=10/60 means 10 requests per rolling 60s window.
    rate_limits_csv: str = "free=10/60,pro=120/60,enterprise=1000/60"
    # On a Redis error, allow the request rather than blackout the whole API.
    rate_limit_fail_open: bool = True

    # ----- Guardrails (Phase 5) -----
    # Tiny classifier model used only when a keyword rule fires (escalation).
    guardrail_classifier_model: str = "claude-sonnet-4-6"
    guardrail_classifier_max_tokens: int = 24

    # ----- CORS / embeddable widget (Phase 7) -----
    # Comma-separated allowed origins for browser installs ("" = none, "*" =
    # allow all — dev default). In production set this to the real origins that
    # embed the widget so a tenant page must be explicitly allow-listed.
    cors_origins: str = "*"

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