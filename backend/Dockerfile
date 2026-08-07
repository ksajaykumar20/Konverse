# Konverse backend image. Shared by the `backend` (uvicorn) and
# `celery-worker` services in docker-compose — they differ only in the start
# command, so both scale as independent, stateless replicas.
#
# Pin Python to 3.12-slim for wide binary-wheel availability across
# asyncpg/qdrant-client/redis. Local dev may use 3.14; the container pins its
# own interpreter for reproducibility.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps first (layer stays cached across code edits).
# libpq5 is only needed if you go pgbouncer/client-native pool later.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps before copying source so code changes don't re-install.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Default = run the API. Overridden by the celery-worker service's `command`.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]