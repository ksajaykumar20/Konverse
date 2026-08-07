"""SQLAlchemy declarative base shared by every model.

Importing `app.models` at app boot registers all tables against `Base.metadata`
so `create_all` and Alembic autogenerate see the full schema.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass