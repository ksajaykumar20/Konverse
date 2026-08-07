"""Tests for the platform-admin console (Phase: admin + management).

`require_admin` reads the GLOBAL get_settings() (the process singleton), so we
monkeypatch `app.services.auth.get_settings` to turn the admin key on/off.
"""
import pytest

from app.config import Settings

ADMIN = {"X-Admin-Key": "admin-secret"}
NO_KEY = {}


def _enable_admin(monkeypatch) -> Settings:
    s = Settings(admin_api_key="admin-secret")
    monkeypatch.setattr("app.services.auth.get_settings", lambda: s)
    return s


async def _mk_tenant(client, name="Acme Co"):
    r = await client.post("/api/tenants", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


# --- auth gating ------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_disabled_when_no_key(client, monkeypatch):
    # Pin an empty key explicitly so this is hermetic even if a real
    # backend/.env (with ADMIN_API_KEY) exists in the working directory.
    monkeypatch.setattr(
        "app.services.auth.get_settings", lambda: Settings(admin_api_key="")
    )
    r = await client.get("/api/admin/tenants")
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_admin_verify_is_db_free(client, monkeypatch):
    """/verify validates the key without touching the DB, so login works even
    with Postgres down."""
    _enable_admin(monkeypatch)
    # wrong key -> 401
    assert (await client.get("/api/admin/verify", headers={"X-Admin-Key": "nope"})).status_code == 401
    # correct key -> 200 (no DB hit required)
    r = await client.get("/api/admin/verify", headers=ADMIN)
    assert r.status_code == 200 and r.json()["admin"] is True


@pytest.mark.asyncio
async def test_admin_requires_valid_key(client, monkeypatch):
    _enable_admin(monkeypatch)
    assert (await client.get("/api/admin/tenants")).status_code == 401
    assert (await client.get("/api/admin/tenants", headers={"X-Admin-Key": "wrong"})).status_code == 401
    r = await client.get("/api/admin/tenants", headers=ADMIN)
    assert r.status_code == 200
    assert "tenants" in r.json()


# --- list + counts ---------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_lists_all_tenants_with_usage(client, monkeypatch):
    _enable_admin(monkeypatch)
    await _mk_tenant(client, "Alpha")
    await _mk_tenant(client, "Beta")

    r = await client.get("/api/admin/tenants", headers=ADMIN)
    assert r.status_code == 200
    rows = r.json()["tenants"]
    names = {t["name"] for t in rows}
    assert {"Alpha", "Beta"} <= names
    for t in rows:
        assert {"document_count", "message_count", "session_count", "last_active"} <= set(t)


@pytest.mark.asyncio
async def test_admin_search_filters(client, monkeypatch):
    _enable_admin(monkeypatch)
    await _mk_tenant(client, "Alpha Store")
    await _mk_tenant(client, "Bravo Clinic")

    r = await client.get("/api/admin/tenants", headers=ADMIN, params={"q": "Alpha"})
    rows = r.json()["tenants"]
    assert len(rows) == 1 and rows[0]["name"] == "Alpha Store"


# --- onboard / update / disable / regenerate --------------------------------


@pytest.mark.asyncio
async def test_admin_create_returns_key_once(client, monkeypatch):
    _enable_admin(monkeypatch)
    r = await client.post(
        "/api/admin/tenants",
        headers=ADMIN,
        json={"name": "NewCo", "rate_limit_plan": "pro"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["api_key"].startswith("sk_")
    assert body["rate_limit_plan"] == "pro"

    # The returned key authenticates that tenant (single view of truth).
    me = await client.get("/api/tenants/me", headers={"X-API-Key": body["api_key"]})
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_admin_update_can_disable_and_disabled_blocks_peer(client, monkeypatch):
    _enable_admin(monkeypatch)
    t = await _mk_tenant(client)
    # disable via admin PATCH
    r = await client.patch(
        f"/api/admin/tenants/{t['id']}",
        headers=ADMIN,
        json={"is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # the tenant API key now fails auth (disabled)
    me = await client.get("/api/tenants/me", headers={"X-API-Key": t["api_key"]})
    assert me.status_code == 403


@pytest.mark.asyncio
async def test_admin_regenerate_invalidates_old_key(client, monkeypatch):
    _enable_admin(monkeypatch)
    t = await _mk_tenant(client)

    r = await client.post(f"/api/admin/tenants/{t['id']}/regenerate-key", headers=ADMIN)
    assert r.status_code == 200
    new_key = r.json()["api_key"]
    assert new_key != t["api_key"]

    assert (await client.get("/api/tenants/me", headers={"X-API-Key": t["api_key"]})).status_code == 401
    assert (await client.get("/api/tenants/me", headers={"X-API-Key": new_key})).status_code == 200


# --- guarded hard delete ----------------------------------------------------


@pytest.mark.asyncio
async def test_admin_hard_delete_requires_confirm(client, monkeypatch):
    _enable_admin(monkeypatch)
    t = await _mk_tenant(client)
    r = await client.delete(f"/api/admin/tenants/{t['id']}", headers=ADMIN)
    assert r.status_code == 400  # confirm=hard not given, data preserved
    assert (await client.get("/api/admin/tenants", headers=ADMIN)).status_code == 200


@pytest.mark.asyncio
async def test_admin_hard_delete_purges_and_cascades(client, monkeypatch):
    _enable_admin(monkeypatch)
    t = await _mk_tenant(client)

    purged = {"qdrant": [], "files": []}

    async def fake_delete_points(settings, tenant_id):
        purged["qdrant"].append(tenant_id)

    def fake_delete_doc(rel):
        purged["files"].append(rel)

    monkeypatch.setattr("app.services.tenants.qdrant.delete_tenant_points", fake_delete_points)
    monkeypatch.setattr("app.services.tenants.storage.delete_document", fake_delete_doc)

    r = await client.delete(
        f"/api/admin/tenants/{t['id']}",
        headers=ADMIN,
        params={"confirm": "hard"},
    )
    assert r.status_code == 204
    assert purged["qdrant"] == [t["id"]]

    # tenant is gone from the admin list
    rows = (await client.get("/api/admin/tenants", headers=ADMIN)).json()["tenants"]
    assert t["id"] not in {row["id"] for row in rows}
    # and its key no longer authenticates
    assert (await client.get("/api/tenants/me", headers={"X-API-Key": t["api_key"]})).status_code == 401


# --- drill-in ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_documents_and_sessions_drill_in(client, monkeypatch):
    _enable_admin(monkeypatch)
    t = await _mk_tenant(client)
    docs = await client.get(f"/api/admin/tenants/{t['id']}/documents", headers=ADMIN)
    assert docs.status_code == 200 and isinstance(docs.json(), list)
    sess = await client.get(f"/api/admin/tenants/{t['id']}/sessions", headers=ADMIN)
    assert sess.status_code == 200 and "sessions" in sess.json()