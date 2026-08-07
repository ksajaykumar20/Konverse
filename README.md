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

## Phase 2 — tenants & auth

**Schema** (SQLAlchemy + Alembic, Postgres-targeted): `tenants`, `documents`,
`chat_sessions`, `messages`. UUID PKs throughout; every tenant-scoped row carries
a denormalized `tenant_id` FK + index for cheap per-tenant queries and clean
Qdrant shard-by-tenant later.

**API** (all under `/api`):

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/tenants` | none | create a tenant, returns `api_key` **once** |
| GET | `/tenants/me` | `X-API-Key` | current tenant config |
| GET | `/tenants/{id}` | `X-API-Key` | own tenant; others → 404 |
| PATCH | `/tenants/{id}` | `X-API-Key` | update name/industry/system_prompt/guardrails/plan |

Keys are long random `sk_...` tokens; only their **sha256 hash** is stored, so a
DB leak yields no usable credentials. The API-key dependency already calls a
`RateLimiter` hook (a no-op stub now) so Phase 5 drops in Redis token-bucket
limiting without touching routers.

### Run the migration (needs Postgres)
```bash
cp .env.example .env            # ensure DATABASE_URL points at Postgres
docker compose up -d db         # or your local Postgres
cd backend
.venv/Scripts/python -m alembic upgrade head
```
**Verify the migration SQL offline** (no DB needed):
```bash
.venv/Scripts/python -m alembic upgrade head --sql
```

### Curl smoke test (once DB is up)
```bash
curl -s -X POST localhost:8000/api/tenants \
  -H 'Content-Type: application/json' -d '{"name":"Acme","industry":"ecommerce"}'
```
Save the returned `api_key`, then:
```bash
curl -s localhost:8000/api/tenants/me -H 'X-API-Key: <api_key>'
```

---

## Phase 3 — document ingestion (async via Celery)

Uploads never block the API: the request saves the file and enqueues a Celery
job, and an independent worker extracts → chunks → embeds → upserts to Qdrant.

**Pipeline:** `POST /api/ingest/{tenant_id}` (multipart file) → save to
`STORAGE_DIR` → insert `documents` row (`processing`) → `ingest_document.delay()`
→ worker runs `run_ingestion` → status flips to `indexed`/`failed`.

| Endpoint | Auth | Purpose |
|---|---|---|
| POST `/api/ingest/{tenant_id}` | `X-API-Key` | upload → 202, status `processing` |
| GET `/api/documents/{tenant_id}` | `X-API-Key` | list docs + status (dashboard poll) |

**Chosen in onboarding:** extraction via **PyMuPDF + python-docx** (PDF/DOCX;
CSV/TXT/MD via stdlib); chunking **1000 chars / 200 overlap**
(`RecursiveCharacterTextSplitter`); **one Qdrant collection** with a
`tenant_id` payload filter on every point (see `app/services/qdrant.py`).

### Local testing (no Docker)
- `pytest` covers the full pipeline with mocked embeddings/Qdrant on SQLite:
  upload→enqueue, `indexed` on success, `failed` on error.
- 13 unit tests total across Phases 1–3 all pass.

### Live end-to-end (needs Redis + Qdrant + Postgres + OpenAI key)
```bash
# .env: OPENAI_API_KEY=sk-..., QDRANT_URL, DATABASE_URL, STORAGE_DIR
docker compose up -d db qdrant redis                # infra
docker compose up celery-worker                     # worker
.venv/Scripts/python -m uvicorn app.main:app --reload
# create tenant (Phase 2), then:
curl -s -X POST localhost:8000/api/ingest/<tenant_id> \
  -H 'X-API-Key: <api_key>' -F 'file=@./sample.txt'
# poll until indexed:
curl -s localhost:8000/api/documents/<tenant_id> -H 'X-API-Key: <api_key>'
```

The status `processing → indexed/failed` is polled by the dashboard (Phase 6).
Scale model: **more Celery worker replicas = more ingestion throughput**,
independent of the chat-serving API replicas.

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