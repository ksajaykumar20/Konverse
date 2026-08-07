"""Local document storage.

Uploaded bytes are written to `STORAGE_DIR` under a UUID-prefixed filename and
the *relative* path is stored in `documents.storage_path`. Keeping storage
behind these two functions means Phase 10 can swap the backend to S3 without
touching routers or the worker.
"""
from pathlib import Path
import uuid

from app.config import get_settings


def _base_dir() -> Path:
    base = Path(get_settings().storage_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_upload(data: bytes, original_filename: str) -> str:
    """Persist file bytes; return the relative storage path (safe to store)."""
    # Strip path separators so a crafted filename can't escape storage_dir.
    safe_name = Path(original_filename).name
    rel = f"{uuid.uuid4().hex}-{safe_name}"
    target = _base_dir() / rel
    target.write_bytes(data)
    return rel


def read_upload(rel_path: str) -> bytes:
    """Read back a stored file by its relative path."""
    return (_base_dir() / rel_path).read_bytes()


def delete_document(rel_path: str | None) -> None:
    """Remove a stored document by its relative path.

    Missing files are ignored (idempotent) so purging a tenant whose file was
    already removed doesn't raise.
    """
    if not rel_path:
        return
    try:
        (_base_dir() / rel_path).unlink(missing_ok=True)
    except OSError:
        # A path that escapes storage_dir would raise; swallow so a single
        # bad file doesn't abort an admin purge mid-way.
        pass