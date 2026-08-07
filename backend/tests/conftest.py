"""pytest fixtures — in-memory SQLite app client (no Docker/Postgres needed)."""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import base as db_base
from app.db.session import get_db
from app.main import create_app

# Ensure all tables are registered before create_all.
import app.models  # noqa: F401


@pytest_asyncio.fixture
async def client():
    """FastAPI test client backed by an in-memory SQLite DB.

    Uses StaticPool so every session shares one connection (required for
    in-memory SQLite across async sessions). The `get_db` dependency is
    overridden to point at this DB; the production engine is never touched.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(db_base.Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = create_app(Settings())
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c._factory = session_factory
        yield c

    await engine.dispose()