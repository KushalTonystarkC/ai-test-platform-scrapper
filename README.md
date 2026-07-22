# Knowledge Base Generation System

Phase 1 of the AI-powered Question Bank Platform. Ingests exam materials (books, previous-year papers, syllabi) into a structured PostgreSQL knowledge base with embeddings and hybrid search.

## Scope

**In scope:** document upload, PDF extraction, semantic chunking, LLM metadata extraction, embeddings, hybrid search.

**Out of scope:** question generation, AI agents, test generation, auth, frontend.

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

## Quick start

```bash
# 1. Start PostgreSQL (pgvector + pg_trgm)
docker compose up -d

# 2. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Configure
cp .env.example .env

# 4. Migrate
alembic upgrade head

# 5. Seed exams
python -m scripts.seed_exams

# 6. Run API
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

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

Defaults use **Gemini**. Set `GEMINI_API_KEY` in `.env`.

| Provider | Values | Default models |
|----------|--------|----------------|
| LLM | `gemini`, `mock`, `openai` | `gemini-2.5-flash` |
| Embedding | `gemini`, `mock`, `openai` | `gemini-embedding-001` (dim 1536) |

Interfaces live under `app/providers/`. Swap implementations without touching services.

```bash
# Gemini (default)
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your-key

# Local/tests without API calls
LLM_PROVIDER=mock
EMBEDDING_PROVIDER=mock
```

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
| GET/POST | `/api/v1/exams` | List / create exams |

## Tests

```bash
pytest -q
```
