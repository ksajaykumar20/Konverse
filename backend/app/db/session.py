"""Async engine + session factory and the FastAPI DB dependency.

Connection pooling is on by default (`pool_pre_ping` avoids handing out dead
connections after a DB restart) so many concurrent API replicas share a bounded
set of connections. A production scale-up adds pgbouncer in front of Postgres —
the app code does not change.

Tests override the `get_db` dependency with an in-memory SQLite session, which
is why the engine is built lazily here rather than hard-wired into routers.
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    _engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a scoped async session per request."""
    async with AsyncSessionLocal() as session:
        yield session