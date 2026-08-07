"""Tenant model — the root of every tenant-scoped record in Konverse."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    industry: Mapped[str] = mapped_column(String(100), default="", nullable=False)

    # sha256 of the API key. Plaintext is returned once at creation and never
    # stored — a DB leak does not expose usable credentials.
    api_key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )

    # Pre-shared prompt for the RAG chat (Phase 4) + guardrail config (Phase 5).
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    guardrail_rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Billing/plan placeholder read by the rate limiter (Phase 5).
    rate_limit_plan: Mapped[str] = mapped_column(String(50), default="free")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )