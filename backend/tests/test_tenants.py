"""Tests for tenant CRUD + isolation. Run against in-memory SQLite."""
import pytest
from httpx import AsyncClient

API_KEY_HDR = "X-API-Key"


async def create_tenant(
    client: AsyncClient, name: str, industry: str = ""
) -> dict:
    resp = await client.post(
        "/api/tenants", json={"name": name, "industry": industry}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def headers(key: str = "") -> dict:
    return {"X-API-Key": key} if key else {}


@pytest.mark.asyncio
async def test_create_tenant_returns_key_once(client):
    body = await create_tenant(client, "Acme")
    assert body["name"] == "Acme"
    assert body["slug"] == "acme"
    assert body["api_key"].startswith("sk_")  # shown once
    assert "api_key_hash" not in body


@pytest.mark.asyncio
async def test_me_round_trip(client):
    body = await create_tenant(client, "Shop")
    key = body["api_key"]
    resp = await client.get("/api/tenants/me", headers=headers(key))
    assert resp.status_code == 200
    assert resp.json()["id"] == body["id"]
    assert resp.json()["slug"] == "shop"


@pytest.mark.asyncio
async def test_missing_header_401(client):
    assert (await client.get("/api/tenants/me")).status_code == 401


@pytest.mark.asyncio
async def test_invalid_key_401(client):
    resp = await client.get("/api/tenants/me", headers=headers("sk_bogus"))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cross_tenant_read_is_404(client):
    a = await create_tenant(client, "TenantA")
    b = await create_tenant(client, "TenantB")
    # Tenant B tries to read Tenant A's config -> 404 (no existence leak).
    resp = await client.get(f"/api/tenants/{a['id']}", headers=headers(b["api_key"]))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_own_tenant(client):
    a = await create_tenant(client, "TenantA")
    resp = await client.patch(
        f"/api/tenants/{a['id']}",
        headers=headers(a["api_key"]),
        json={"system_prompt": "Only answer from docs", "industry": "ecommerce"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["system_prompt"] == "Only answer from docs"
    assert data["industry"] == "ecommerce"


@pytest.mark.asyncio
async def test_inactive_tenant_forbidden(client):
    a = await create_tenant(client, "TenantA")
    # Deactivate self; then the key must be refused.
    deact = await client.patch(
        f"/api/tenants/{a['id']}",
        headers=headers(a["api_key"]),
        json={"is_active": False},
    )
    assert deact.status_code == 200
    resp = await client.get("/api/tenants/me", headers=headers(a["api_key"]))
    assert resp.status_code == 403