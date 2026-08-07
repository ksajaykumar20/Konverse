Konverse

A multi-tenant AI chatbot platform powered by Retrieval-Augmented Generation (RAG).

Konverse lets any business — ecommerce, healthcare, or otherwise — plug in its own knowledge base (products, policies, FAQs, department info) and instantly get a branded, grounded AI assistant that answers only from that business's own data. One backend, infinite tenants: what changes per business is configuration and content, not code.

Built with FastAPI, Qdrant, PostgreSQL, Redis, Celery, and Anthropic's Claude, with a Next.js + shadcn/ui dashboard — designed to scale from a single demo tenant to many concurrent businesses without a rewrite.

Table of Contents
Why Konverse
Features
Architecture
Tech Stack
Project Structure
Getting Started
Environment Variables
API Overview
Multi-Tenancy & Data Isolation
Guardrails
Roadmap
Contributing
License
Why Konverse

Most chatbot demos hardcode business logic into the prompt or the codebase. Konverse takes a different approach: the LLM never "memorizes" a business — every answer is generated fresh from that tenant's own indexed documents at query time. This means:

No retraining — add or update a document, and the bot's knowledge updates immediately
Strict data isolation — one tenant's data is never visible to another tenant's users
Same backend, any industry — an ecommerce store and a hospital use the identical pipeline; only their uploaded content and configured guardrails differ
Features
🔌 Bring-your-own knowledge base — upload PDFs, DOCX, CSVs, or plain text per tenant
🧠 RAG-grounded answers — responses are generated only from retrieved, relevant context
🏢 True multi-tenancy — isolated vector search per tenant, enforced at the query level
⚡ Streaming responses — answers appear token-by-token via Server-Sent Events
🛡️ Configurable guardrails — keyword-triggered safe redirects for regulated industries (e.g., no medical advice from a hospital bot)
🚦 Per-tenant rate limiting — Redis-backed protection against abuse and runaway cost
🗂️ Async ingestion — document processing runs in background workers, never blocks the API
💬 Embeddable widget — a framework-free <script> tag any website can drop in
📊 Dashboard — businesses self-serve: upload docs, edit their assistant's tone/rules, view chat logs and unanswered questions
📈 Built to scale — stateless API, externalized cache/session state, containerized services
Architecture
                     ┌─────────────────────┐
                     │   Client Dashboard   │  (Next.js + shadcn/ui)
                     └──────────┬───────────┘
                                │
                     ┌──────────▼───────────┐
                     │     FastAPI Backend   │
                     └───┬───────────────┬───┘
                         │               │
              ┌──────────▼─────┐   ┌─────▼──────────┐
              │  Celery Worker  │   │  Redis (cache,  │
              │ (async ingest)  │   │  rate limit,    │
              └──────────┬──────┘   │  job broker)    │
                         │           └─────────────────┘
              ┌──────────▼──────────┐
              │   Qdrant (vectors)   │  ← isolated per tenant_id
              └──────────┬──────────┘
                         │
     End User ──► Chat Widget ──► /chat/{tenant_id} ──► Retriever ──► Claude API
                                                             │
                                              ┌──────────────▼──────────────┐
                                              │ PostgreSQL: tenants, docs,   │
                                              │ sessions, messages, config   │
                                              └──────────────────────────────┘

Each request flow:

A business uploads documents via the dashboard → stored → queued to a Celery worker
The worker extracts text, chunks it, generates embeddings, and upserts into Qdrant tagged with tenant_id
An end user asks a question via the widget or dashboard playground
The backend embeds the query, retrieves top-k relevant chunks filtered strictly by tenant_id, and builds a grounded prompt using that tenant's configured system prompt and guardrails
Claude generates a response, streamed back to the user, and the exchange is logged for analytics
Tech Stack
Layer	Technology
LLM	Anthropic Claude API
Embeddings	OpenAI text-embedding-3-small
Vector database	Qdrant
Relational database	PostgreSQL (via SQLAlchemy)
Cache / rate limiting / job broker	Redis
Background jobs	Celery
Backend API	FastAPI (async, Python)
Chunking	LangChain RecursiveCharacterTextSplitter
Dashboard	Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui
Embeddable widget	Vanilla JavaScript (framework-free)
Local orchestration	Docker Compose
Project Structure
/backend
  /app
    /routers        # ingest.py, chat.py, tenants.py, health.py
    /services        # chunking.py, embeddings.py, retrieval.py, llm.py, cache.py, ratelimit.py
    /workers          # Celery tasks for document ingestion
    /models           # SQLAlchemy models
    /db               # DB session, Alembic migrations
    main.py
  requirements.txt
  Dockerfile
/dashboard             # Next.js app — tenant setup, doc upload, prompt/guardrail editor, chat logs, live chat playground
/widget                 # Embeddable vanilla-JS chat widget
docker-compose.yml
.env.example
README.md
Getting Started
Prerequisites
Docker & Docker Compose
An Anthropic API key
An OpenAI API key (for embeddings) — or a configured local embedding alternative
Node.js 18+ (for the dashboard, if running outside Docker)
1. Clone the repo
bash
git clone https://github.com/<your-username>/konverse.git
cd konverse
2. Configure environment variables
bash
cp .env.example .env

Fill in the required values — see Environment Variables below.

3. Start the backend services
bash
docker-compose up --build

This spins up:

PostgreSQL
Qdrant
Redis
FastAPI backend (http://localhost:8000)
Celery worker

Confirm everything is healthy:

bash
curl http://localhost:8000/health
4. Run database migrations
bash
docker-compose exec backend alembic upgrade head
5. Start the dashboard
bash
cd dashboard
npm install
npm run dev

Visit http://localhost:3000.

6. Try the embeddable widget

Open widget/test.html in a browser, pointed at a tenant ID created via the dashboard or API.

Environment Variables
Variable	Description
ANTHROPIC_API_KEY	Claude API key
OPENAI_API_KEY	Used for generating embeddings
DATABASE_URL	PostgreSQL connection string
QDRANT_URL	Qdrant instance URL
REDIS_URL	Redis connection string (cache, rate limiting, Celery broker)
CELERY_BROKER_URL	Usually same as REDIS_URL
RATE_LIMIT_DEFAULT	Default requests/minute per tenant

See .env.example for the full list and defaults.

API Overview
Method	Endpoint	Description
GET	/health	Service health check (DB, Qdrant, Redis)
POST	/tenants	Create a new tenant, returns API key
GET	/tenants/{id}	Fetch tenant configuration
PATCH	/tenants/{id}	Update system prompt, guardrails, settings
POST	/ingest/{tenant_id}	Upload a document for async processing
GET	/documents/{tenant_id}	List a tenant's documents and indexing status
POST	/chat/{tenant_id}	Send a query, receive a streamed, grounded response
GET	/chat/{tenant_id}/history/{session_id}	Fetch a chat session's history

Full request/response schemas are documented via FastAPI's auto-generated docs at http://localhost:8000/docs.

Multi-Tenancy & Data Isolation

Every vector stored in Qdrant carries a tenant_id payload field, and every retrieval query filters strictly by that field — a tenant's chatbot can never surface another tenant's data, regardless of query phrasing. Tenant configuration (system prompt, guardrail rules, rate limits) lives in PostgreSQL, scoped by tenant_id at the row level.

Guardrails

For regulated industries (e.g., healthcare), tenants can configure keyword-triggered guardrails that intercept risky queries before they reach the LLM — for example, redirecting symptom-related questions to an emergency contact message instead of generating a response. This is an MVP, keyword-based approach; see the roadmap for planned upgrades to intent-based classification.

Roadmap
 Agentic tool-use (LangGraph) — live order lookups, appointment booking, and other actions beyond static document retrieval
 Production infrastructure — Kubernetes/ECS deployment, Qdrant clustering, managed Postgres with read replicas, autoscaling
 Advanced guardrails — intent classification instead of keyword matching
 RAG quality evaluation — automated retrieval relevance and answer faithfulness scoring
 Usage-based billing — tenant plans/tiers mapped to rate limits and features
Contributing

Contributions are welcome. Please open an issue to discuss significant changes before submitting a pull request. Run tests and linting locally before opening a PR.

License
MIT
