"""Create all tables for the local no-Docker profile.

Production uses Alembic migrations against Postgres. For the Docker-free local
stack we run on SQLite, which needs no migration tool — this script just applies
`Base.metadata.create_all` against whatever DATABASE_URL the current `.env` says.

Usage (from backend/):
    ./.venv/Scripts/python.exe -m scripts.init_db

Idempotent: `create_all` skips tables that already exist.
"""
import asyncio
import sys
from pathlib import Path

# Allow `python -m scripts.init_db` from backend/ without an install step.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db import base as db_base
from app.db.session import _engine

import app.models  # noqa: F401  (register all models on Base.metadata)


async def main() -> None:
    settings = get_settings()
    print(f"[init_db] DATABASE_URL = {settings.database_url}")
    async with _engine.begin() as conn:
        await conn.run_sync(db_base.Base.metadata.create_all)
    print("[init_db] tables ensured.")


if __name__ == "__main__":
    asyncio.run(main())
