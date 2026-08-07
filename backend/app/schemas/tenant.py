"""Tenant request/response schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    """Body for POST /tenants."""

    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9\-]+$")
    industry: str = Field(default="", max_length=100)
    system_prompt: str | None = Field(default=None)
    rate_limit_plan: str = Field(default="free", max_length=50)


class TenantCreateResponse(BaseModel):
    """Returned to the creator. `api_key` appears exactly once."""

    id: uuid.UUID
    name: str
    slug: str
    industry: str
    api_key: str  # plaintext — shown once, then only its hash is stored
    rate_limit_plan: str
    is_active: bool
    created_at: datetime


class TenantRead(BaseModel):
    """Safe tenant view for authentication-locked reads (no api_key)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    industry: str
    system_prompt: str
    guardrail_rules: dict
    rate_limit_plan: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TenantUpdate(BaseModel):
    """Body for PATCH /tenants/{id} — all fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    system_prompt: str | None = None
    guardrail_rules: dict | None = None
    rate_limit_plan: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None