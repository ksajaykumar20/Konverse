"""Celery instance + task discovery.

BROKER_URL and RESULT_BACKEND come from Settings (Redis via env). This module
is the single Celery entrypoint; `include` imports `app.worker.tasks` when the
worker boots so its tasks register by name.
"""
from celery import Celery

from app.config import get_settings


def create_celery() -> Celery:
    from app.config import Settings
    settings: Settings = get_settings()

    app = Celery(
        "konverse",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["app.worker.tasks"],
    )

    # Task result TTL + JSON serialization keeps Redis clean and portable.
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        result_expires=86400,  # 24h
        task_track_started=True,
        broker_connection_retry_on_startup=True,
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app = create_celery()