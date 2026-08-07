"""FastAPI application factory for Konverse.

Philosophy (applies from Phase 1 through production):
  * The app is assembled by create_app(), keeping it testable and letting a
    future test harness build it with overridden settings/clients.
  * Lifespan does NOT hard-fail on missing infra: connectivity is reported by
    GET /health rather than crashing at boot. Later phases wire real
    (pooled) clients here, still without blocking startup.
"""
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.lib.logging import setup_logging
from app.routers import admin, chat, health, ingest, tenants
import app.models  # noqa: F401  (register all tables on Base.metadata)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Konverse API",
        version="0.1.0",
        description=(
            "Multi-tenant AI chatbot platform. Phase 1 scaffold: runnable "
            "API skeleton + /health."
        ),
        # Correlation ID middleware — prep child spans/project later.
    )

    # Request-level correlation id so logs can be tied across API calls.
    @app.middleware("http")
    async def add_correlation_id(request, call_next):
        request.state.correlation_id = request.headers.get(
            "X-Correlation-ID", uuid.uuid4().hex
        )
        return await call_next(request)

    app.include_router(health.router, prefix="/api")
    app.include_router(tenants.router, prefix="/api")
    app.include_router(ingest.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")

    # CORS for browser installs (the Phase 7 embeddable widget fetches the
    # backend directly from a tenant page, including the X-API-Key header).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(settings),
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,  # "*" origins + credentials are mutually exclusive
    )

    # Serve the embeddable widget from /static/widget.js. Mount is optional so
    # the app still imports when the repo is laid out differently.
    widget_dir = _widget_dir()
    if widget_dir and widget_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(widget_dir)), name="static")

    return app


def _widget_dir() -> Path | None:
    # <repo>/widget (main.py lives at <repo>/backend/app/main.py).
    return Path(__file__).resolve().parents[2] / "widget"


def _cors_origins(settings: Settings) -> list[str]:
    """Parse cors_origins CSV into a list of origins ("*" passed through)."""
    if not settings.cors_origins:
        return []
    parts = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    return parts


app = create_app()