# Knowledge Base Generation System

Phase 1 of the AI-powered Question Bank Platform. Ingests exam materials (books, previous-year papers, syllabi) into a structured PostgreSQL knowledge base with embeddings and hybrid search.

## Scope

**In scope:** document upload, PDF extraction, semantic chunking, LLM metadata extraction, embeddings, hybrid search, IBPS-style MCQ generation (persisted), Next.js showcase UI (`web/`).

**Out of scope:** AI agents, full test-paper assembly, auth.

## Architecture

Clean Architecture with a reusable service layer (REST / MCP / CLI / workers share the same business logic).

```
app/
  api/           # Thin REST adapters
  core/          # Config, logging, exceptions, DI
  database/      # Engine, session, base
  models/        # SQLAlchemy models
  schemas/       # Pydantic DTOs
  repositories/  # PostgreSQL access only
  services/      # Business logic
  providers/     # Swappable LLM / embedding / PDF / chunking
  search/        # Keyword, semantic, hybrid search
  workers/       # Async task abstraction
  utils/
```

## Prerequisites

Install these on the new machine before starting:

| Tool | Version | Notes |
|------|---------|--------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose) | latest | Runs Postgres (pgvector) and optional Ollama |
| [Python](https://www.python.org/downloads/) | **3.12+** | Backend API |
| [Node.js](https://nodejs.org/) | **20+** (LTS) | Frontend (`web/`); includes `npm` |
| Git | any | Clone the repo |

Optional:

- **~4 GB free RAM** recommended for local embeddings + Ollama (`llama3.2`)
- A Gemini API key only if you switch away from the default local stack

## Run on another machine

### 1. Clone the repo

```bash
git clone <YOUR_REPO_URL> ai-test-platform-scrapper
cd ai-test-platform-scrapper
```

### 2. Start PostgreSQL

```bash
docker compose up -d
```

This starts **pgvector** Postgres on host port **5433** (user `kushal`, password `0000`, DB `question_bank`). Wait until healthy:

```bash
docker compose ps
```

### 3. Install the Python backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[dev,sentence-transformers]"
```

The first install of `sentence-transformers` downloads the embedding model (`BAAI/bge-small-en-v1.5`) — this can take a few minutes.

### 4. Configure environment

```bash
cp .env.example .env
```

Defaults match Docker Compose (`DATABASE_URL` → `localhost:5433`). Edit `.env` only if you change DB credentials, ports, or providers.

### 5. Start Ollama (local LLM)

```bash
docker compose --profile ollama up -d
docker compose --profile ollama exec ollama ollama pull llama3.2
```

Ollama listens on `http://localhost:11434`. No host `ollama` CLI install is required when using the container.

To skip the LLM for a quick smoke test, set in `.env`:

```bash
LLM_PROVIDER=mock
EMBEDDING_PROVIDER=mock
```

### 6. Migrate and seed

```bash
alembic upgrade head
python -m scripts.seed_exams
```

### 7. Run the API

```bash
uvicorn app.main:app --reload
# or: make run
```

- API: http://localhost:8000  
- Swagger docs: http://localhost:8000/docs  

### 8. Run the frontend (optional)

In a **second terminal**:

```bash
cd web
cp .env.local.example .env.local   # points at http://localhost:8000
npm install
npm run dev
```

Open http://localhost:3000 — Overview, Exams, Documents, Search, and Questions.

Ensure the API is running on `:8000` first. CORS allows `http://localhost:3000`.

### Ports used

| Service | Port |
|---------|------|
| FastAPI | 8000 |
| Next.js | 3000 |
| Postgres (Docker) | 5433 → 5432 in container |
| Ollama (Docker) | 11434 |

### Makefile shortcuts

With the venv activated:

```bash
make up        # docker compose up -d
make install   # pip install -e ".[dev]"  (add sentence-transformers separately if needed)
make migrate
make seed
make run
make test
make down
```

### Verify it works

1. Open http://localhost:8000/docs → list exams  
2. Open http://localhost:3000 → upload a PDF under Documents → Process  
3. Generate questions once processing finishes  

### Common issues

| Problem | Fix |
|---------|-----|
| `connection refused` on DB | `docker compose up -d` and confirm port **5433** is free |
| Port 5432 already in use | This project uses **5433** on purpose; leave `DATABASE_URL` as in `.env.example` |
| Ollama / LLM timeouts | Pull `llama3.2`; give the container enough RAM; or use `LLM_PROVIDER=mock` |
| Embedding install fails | Use Python 3.12+; retry `pip install -e ".[sentence-transformers]"` |
| Frontend can't reach API | API on `:8000`; check `web/.env.local` and `CORS_ORIGINS` in `.env` |

## Document pipeline

```
Upload PDF → Store file → DB record (UPLOADED)
         → POST /documents/{id}/process (async)
         → Extract text (page-aware)
         → Semantic chunks (500–800 words, sentence-safe)
         → LLM metadata per chunk
         → Embeddings → pgvector
         → Status: PROCESSED | FAILED
```

## Adding a new exam

1. `POST /api/v1/exams` with code/name (or seed script)
2. Upload PDFs with that `exam_id`
3. Process — no code changes required

## Providers

Defaults use **free local open-source models** — no Gemini/OpenAI API keys required.

| Role | Provider | Default model |
|------|----------|---------------|
| Embedding | `sentence_transformers` | `BAAI/bge-small-en-v1.5` (dim 384) |
| LLM | `ollama` (OpenAI-compatible) | `llama3.2` via `http://localhost:11434/v1` |

Also supported: `mock`, `openai` (any OpenAI-compatible host), `gemini` (optional extra).

```bash
# Local open-source (default)
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama

# Tests / offline without models
LLM_PROVIDER=mock
EMBEDDING_PROVIDER=mock

# Optional Gemini (pip install -e ".[gemini]")
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=1536
GEMINI_API_KEY=your-key
```

If you change `EMBEDDING_DIMENSION`, update the Alembic vector column (or add a migration) and re-process documents.

Interfaces live under `app/providers/`. Swap implementations without touching services.

## Task backends

`TASK_BACKEND=in_memory` (default) runs processing via FastAPI `BackgroundTasks`. Replace with Celery/Dramatiq by implementing `TaskDispatcher` — services stay unchanged.

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/documents/upload` | Upload PDF |
| POST | `/api/v1/documents/{id}/process` | Queue processing |
| GET | `/api/v1/documents` | List documents |
| GET | `/api/v1/documents/{id}` | Document detail |
| GET | `/api/v1/documents/{id}/chunks` | Chunks for a document |
| GET | `/api/v1/search` | Hybrid / keyword / semantic search |
| POST | `/api/v1/questions/generate` | Generate & save MCQs from KB |
| GET | `/api/v1/questions` | List saved questions |
| GET | `/api/v1/questions/{id}` | Get one question |
| GET/POST | `/api/v1/exams` | List / create exams |

### Generate MCQs

After documents are processed:

**Topic mode** (hybrid search for that topic):

```bash
curl -X POST http://localhost:8000/api/v1/questions/generate \
  -H 'Content-Type: application/json' \
  -d '{"exam_id":"<EXAM_UUID>","topic":"RBI monetary policy","count":2,"difficulty":"medium"}'
```

**Whole syllabus mode** (omit `topic` — samples diverse chunks across the exam):

```bash
curl -X POST http://localhost:8000/api/v1/questions/generate \
  -H 'Content-Type: application/json' \
  -d '{"exam_id":"<EXAM_UUID>","count":5}'
```

`count` defaults to **1** (max **10**). Response includes `requested_count` and `generated_count`.

## Tests

```bash
source .venv/bin/activate
pytest -q
```
