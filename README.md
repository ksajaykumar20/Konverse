# Konverse

Multi-tenant AI chatbot platform. Tenants (ecommerce, hospital, …) upload their
own documents; end users get answers grounded **only** in that tenant's data via
a Retrieval-Augmented Generation (RAG) pipeline. Built to scale from one demo
tenant to many concurrent tenants and users without a rewrite.

> **Phase status:** 5 of 8 — guardrails (regulated-industry interception) +
> Redis rate limiting. See the bottom of this file for the roadmap.

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

## Phase 4 — RAG retrieval + streaming chat

`POST /api/chat/{tenant_id}` grounds an answer **exclusively** in the tenant's
own chunks and streams tokens over **Server-Sent Events** (`text/event-stream`),
so no WebSocket/shared state is held across API replicas.

**Flow:** auth (`X-API-Key`, foreign tenants → 404) → create/resume `ChatSession`
→ log the user message → `retrieve()` (embed query via **Redis cache-first**, then
search **Qdrant filtered to `tenant_id == <tenant>`** with `top_k=5`) → decide →
stream.

| SSE event | Payload |
|---|---|
| `session` | `session_id` (for the consumer to resume) |
| `token` | one text delta |
| `done` | final `text`, `was_answered` bool |

**Decision branch** — threshold `min_score = 0.60`:
- **≥ score:** build a grounded system prompt from the top chunk + tenant
  `system_prompt`, stream Claude (`claude-sonnet-4-6`), persist the assistant
  message with `was_answered=true` + `confidence = max chunk score`.
- **below:** skip the LLM entirely, emit a fixed fallback ("I don't have that
  information…"), persist `was_answered=false`. No token spend on garbage.

**Caching:** embeddings are cached in Redis (key = `embed:{model}:{tenant_id}:
{sha256(query)}`, 24 h TTL) so repeated questions skip re-embedding. **Retrieval
results are not cached** — per-tenant, per-turn freshness wins over latency here.

**Tenant isolation is query-level:** every Qdrant search carries a `tenant_id`
`FieldCondition`, verified by a dedicated isolation test (two tenants, no cross-
tenant vectors reachable regardless of phrasing).

### Local testing (no Docker)
- 17 unit tests total across Phases 1–4; chat tests mock retrieval + LLM and
  assert: grounded streaming + persistence (`was_answered=true`), the
  low-confidence branch **never calls the LLM**, retrieval carries the right
  `tenant_id` filter, and `/history` returns the transcript.
- `GET /api/chat/{tenant_id}/history/{session_id}` returns the session transcript.

### Live end-to-end (needs Postgres + Redis + Qdrant + OpenAI + Anthropic keys)
```bash
# .env: OPENAI_API_KEY, ANTHROPIC_API_KEY, REDIS_URL, QDRANT_URL, DATABASE_URL
docker compose up -d db qdrant redis && docker compose up celery-worker
.venv/Scripts/python -m uvicorn app.main:app --reload
# create tenant, ingest a doc (Phase 3), wait for status=indexed, then:
curl -sN -X POST localhost:8000/api/chat/<tenant_id> \
  -H 'X-API-Key: <api_key>' -H 'Content-Type: application/json' \
  -d '{"message":"What do you sell?"}'
#   -N keeps curl reading the SSE stream line-by-line as tokens arrive.
```

Scale model: chat is read-mostly and stateless, so **more API replicas = more
concurrent chats**; ingestion stays on the worker pool. Claude keys are read per
call (one client per request) so nothing is pinned to a loop or process.

---

## Phase 5 — guardrails + rate limiting

### Guardrails (regulated-industry interception)
A **hybrid** guard runs in the chat path **before** retrieval, based on the
tenant's `guardrail_rules` JSON (default empty — a no-op for tenants that opt
out). With guardrails enabled:
- **Layer 1 (rules):** cheap keyword/phrase scan per category
  (`medical_diagnosis`, `investment_advice`, …). Zero latency, zero tokens.
- **Layer 2 (escalation):** when a rule fires, a tiny Claude classifier decides
  *refuse* vs *pass* — so paraphrases and innocent keyword coincidences don't
  block real questions. Missing key / classifier error → **refuses (safe)**.
- **On refusal:** the API emits a `guardrail` SSE event (with `category`), a
  fixed refusal message, and `done` with `was_answered=false`. The turn is
  logged as a `Message` with `guardrail_category` set — no retrieval, no
  embedding, no main-model token spend.

Configure per tenant (via `PATCH /tenants/{id}`):
```json
{ "enabled": true, "categories": {
  "medical_diagnosis": { "keywords": ["diagnose", "symptoms of", "my rash"], "enabled": true },
  "investment_advice": { "keywords": ["buy this stock"], "enabled": true }
} }
```

### Rate limiting (Redis sliding-window log)
The Phase 2 stub is now a real limiter on the auth dependency (every protected
route). No routers change.
- **Sliding window log:** one Redis sorted set per limit key; on each request
  purge entries older than the window, count survivors, and deny once the window
  fills. No Redis module required.
- **Keyed per API key hash** (`rl:{plan}:{api_key_hash}`) so each distinct key
  has its own budget — one noisy key can't drain the whole tenant.
- **Plan tiers** from `RATE_LIMITS_CSV` map to `rate_limit_plan`
  (`free=10/60`, `pro=120/60`, `enterprise=1000/60`) — config-only, no migration.
- **Fail-open:** a Redis outage allows requests by default
  (`RATE_LIMIT_FAIL_OPEN=true`) rather than blackouting the API; `429` carries
  a `Retry-After` header for well-behaved clients.

### Local testing (no Docker)
- **29 tests passing** across Phases 1–5. Rate limiting is tested against an
  in-memory fake Redis; an `AllowAll` limiter keeps the shared HTTP client off
  real Redis in the rest of the suite. Asserted: sliding-window allow-then-deny,
  per-key isolation, fail-open, and the HTTP `429` + `Retry-After` path.
- **Migrations:** `0002` adds `messages.guardrail_category`. Verify offline:
  `alembic upgrade head --sql`. Run against Postgres when infra is up.

### Live end-to-end (needs Postgres + Redis)
```bash
cd backend && .venv/Scripts/python -m alembic upgrade head     # apply 0002
# PATCH a tenant's guardrail_rules (above), then send a guarded question:
curl -sN -X POST localhost:8000/api/chat/<tenant_id> \
  -H 'X-API-Key: <api_key>' -H 'Content-Type: application/json' \
  -d '{"message":"please diagnose my rash"}'
# -> SSE: a `guardrail` event, refusal message, was_answered=false.
# Hammer the same key 11+ times quickly (free plan) -> HTTP 429 + Retry-After.
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
| `ANTHROPIC_API_KEY` | LLM + guardrail classifier | Phases 4–5 |
| `RATE_LIMITS_CSV` / `RATE_LIMIT_FAIL_OPEN` | sliding-window limits | Phase 5 |
| `GUARDRAIL_CLASSIFIER_MODEL` / `_MAX_TOKENS` | guardrail escalation | Phase 5 |

---

## Roadmap (phases)

1. ✅ Scaffolding & environment (this)
2. ✅ Database schema + tenant management (SQLAlchemy, Alembic, API-key auth)
3. ✅ Document ingestion pipeline (async, Celery: parse → chunk → embed → Qdrant)
4. ✅ Retrieval + Chat (RAG) with SSE streaming, caching, low-confidence fallback
5. ✅ Guardrails (regulated-industry interception) + Redis rate limiting
6. Dashboard (Next.js + shadcn/ui)
7. Embeddable vanilla-JS chat widget
8. End-to-end validation (2 demo tenants + light concurrent load check)
   _Optional:_ 9. LangGraph agentic tool use · 10. Production scale-out