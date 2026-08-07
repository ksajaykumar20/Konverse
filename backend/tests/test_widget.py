"""Phase 7 tests — static widget serving + CORS for browser installs."""
import pytest


@pytest.mark.asyncio
async def test_static_widget_is_served(client):
    r = await client.get("/static/widget.js")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "")
    assert "Konverse.init" in r.text  # the public API the page calls


@pytest.mark.asyncio
async def test_cors_preflight_permits_api_key_header(client):
    """A browser embed must be able to preflight /api/chat with X-API-Key."""
    r = await client.options(
        "/api/chat/00000000-0000-0000-0000-000000000000",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key, content-type",
        },
    )
    assert r.status_code == 200
    allow_origin = r.headers.get("access-control-allow-origin", "")
    assert "*" in allow_origin or "localhost" in allow_origin
    allow_headers = r.headers.get("access-control-allow-headers", "").lower()
    assert "x-api-key" in allow_headers