"""Service layer: business logic shared by routers and workers.

Kept separate from routers so the same functions are reusable from Celery tasks
(Phase 3) and the dashboard (Phase 6) without HTTP concerns.
"""