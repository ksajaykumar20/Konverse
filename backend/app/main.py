"""FastAPI application factory for Konverse.

Philosophy (applies from Phase 1 through production):
  * The app is assembled by create_app(), keeping it testable and letting a
    future test harness build it with overridden settings/clients.
  * Lifespan does NOT hard-fail on missing infra: connectivity is reported by
    GET /health rather than crashing at boot. Later phases wire real
    (pooled) clients here, still without blocking startup.
"""
import uuid

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.lib.logging import setup_logging
from app.routers import chat, health, ingest, tenants
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

    return app


app = create_app()