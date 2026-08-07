"""Aggregate model imports so Base.metadata is fully populated.

Any consumer that needs the whole schema (Alembic autogenerate, tests that call
`Base.metadata.create_all`, scripts) should import this package.
"""
from app.models.tenant import Tenant  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.chat import ChatSession, Message  # noqa: F401