# Konverse

Multi-tenant AI chatbot platform. Tenants (ecommerce, hospital, …) upload their
own documents; end users get answers grounded **only** in that tenant's data via
a Retrieval-Augmented Generation (RAG) pipeline. Built to scale from one demo
tenant to many concurrent tenants and users without a rewrite.

> **Phase status:** 1 of 8 — runnable API + `/health` skeleton, Celery worker
> stub, and a Docker Compose stack. See the bottom of this file for the roadmap.

---

## Architecture at a glance

```
                      ┌──────────────────────────────┐
   Backend (FastAPI)  │  POST /chat  (SSE stream)    │
   stateless, scales │  POST /ingest (async enqueue) │
   horizontally       └──────────┬───────────────────┘
                                 │
              ┌──────────────────┼───────────────────┐
              │                  │                    │
        ┌─────▼────┐      ┌──────▼─────┐      ┌──────▼─────┐
        │ Postgres │◄─────┤  Redis     │◄─────┤  Qdrant    │
        │ metadata │ cache│ (cache/CL/ │ RSV  │ vector store│
        │ + logging│      │  broker)   │ fetch│ (tenant-    │
        └──────────┘      └────────────┘      │  tagged)    │
                                               └───────┬────┘
                                                       │ (async)
                                              ┌────────▼────────┐
                                              │ Celery worker(s)│ parse→chunk→embed→upsert
                                              └─────────────────┘
```

**Phase 1 components**

| Service | Image (dev) | Role | How it scales independently |
|---|---|---|---|
| `db` | `postgres:16` | Relational store: tenants, docs, messages | → managed Postgres + read replicas / pgbouncer in prod |
| `qdrant` | `qdrant/qdrant` | Vector store for tenant-filtered chunks | → Qdrant Cloud / clustered nodes; shard by tenant |
| `redis` | `redis:7` | Cache + rate limiting + Celery broker | → managed Redis (ElastiCache/Upstash) for HA |
| `backend` | FastAPI + uvicorn | Stateless HTTP API | → add replicas behind a load balancer; no shared state |
| `celery-worker` | Celery | Async ingestion/embedding off the request path | → add worker replicas independently; they don't serve chat |

**Scaling model rationale.** The API and the worker are the same codebase built
into one image, differing only in start command. Because every instance is
stateless and all shared state lives in Postgres/Qdrant/Redis, you scale the
read path (chat) by adding API replicas and the write path (ingestion) by adding
Celery workers — independently and without a rewrite.

---

## Local setup

### Prerequisites
- **Docker + Docker Compose** (Compose v2). If Docker isn't installed yet,
  install [Docker Desktop](https://docker.com/products/docker-desktop) (enables
  the WSL2 backend — required for Qdrant, which has no native Windows build).
- Python 3.12+ (optional: only if you want to run the API/worker natively).

### 1. Configure environment
```bash
cp .env.example .env
```
Fill in API keys **later** (Phases 3–4); Phase 1 needs no secrets. Never commit
`.env`.

### 2. Start the stack
```bash
docker compose up --build
```
This runs Postgres, Qdrant, Redis, the FastAPI app on `:8000`, and one Celery
worker. First build pulls images / installs deps and takes a few minutes.

### 3. Verify health
```bash
curl http://localhost:8000/api/health
```
Expected — **200** when all three services are green:
```json
{ "status": "ok", "checks": {
  "postgres": {"status":"ok"}, "qdrant": {"status":"ok"}, "redis": {"status":"ok"} } }
```
if any dependency is down (e.g. worker-only Compose), you get **503** with a
`status: degraded` payload naming the failing service — useful for orchestrators.

### Running the backend natively (no Docker) — for the API + worker
Only possible once Postgres/Qdrant/Redis are reachable (Phase 1 cannot run them
natively on Windows — Qdrant ships no Windows binary). Once you have them running:
```bash
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --reload          # API :8000
.venv/Scripts/python -m celery -A app.worker.celery_app.celery_app worker -l info
```
> On native Windows, Celery's default `prefork` pool is unavailable — pass
> `--pool=solo --concurrency=1` if you run the worker on the host. The Docker
> worker (Linux) uses `prefork` and needs no flags.

### Celery smoke test (proves the worker picks up jobs)
```bash
# In a python shell:
from app.worker.tasks import add
r = add.delay(2, 3)      # enqueue via Redis broker
r.get(timeout=5)          # -> 5  (wait: worker consumed and executed)
```

---

## Config reference

All env vars are documented in [`.env.example`](.env.example). Key ones:

| Var | Purpose | Later used by |
|---|---|---|
| `DATABASE_URL` | Postgres (SQLAlchemy async) | Phase 2 |
| `REDIS_URL` | cache + rate limiting | Phases 4–5 |
| `QDRANT_URL` | vector store | Phase 3 |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Celery on Redis | Phase 3 |
| `OPENAI_API_KEY` | embeddings | Phase 3 |
| `ANTHROPIC_API_KEY` | LLM (claude-sonnet-4-6) | Phase 4 |

---

## Roadmap (phases)

1. ✅ Scaffolding & environment (this)
2. Database schema + tenant management (SQLAlchemy, Alembic, API-key auth)
3. Document ingestion pipeline (async, Celery: parse → chunk → embed → Qdrant)
4. Retrieval + Chat (RAG) with SSE streaming, caching, low-confidence fallback
5. Guardrails (regulated-industry interception) + Redis rate limiting
6. Dashboard (Next.js + shadcn/ui)
7. Embeddable vanilla-JS chat widget
8. End-to-end validation (2 demo tenants + light concurrent load check)
   _Optional:_ 9. LangGraph agentic tool use · 10. Production scale-out