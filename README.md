# Knowledge Base Generation System

Phase 1 of the AI-powered Question Bank Platform. Ingests exam materials (books, previous-year papers, syllabi) into a structured PostgreSQL knowledge base with embeddings and hybrid search.

## Scope

**In scope:** document upload, PDF extraction, semantic chunking, LLM metadata extraction, embeddings, hybrid search, IBPS-style MCQ generation (persisted).

**Out of scope:** AI agents, full test-paper assembly, auth, frontend.

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

# 2. Install (includes local sentence-transformers embeddings)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,sentence-transformers]"

# 3. Configure
cp .env.example .env

# 4. Start Ollama in Docker and pull an LLM (free, local)
docker compose --profile ollama up -d
docker compose --profile ollama exec ollama ollama pull llama3.2
# (Host `ollama` CLI is not required when using the container.)

# 5. Migrate
alembic upgrade head

# 6. Seed exams
python -m scripts.seed_exams

# 7. Run API
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
  -d '{"exam_id":"<EXAM_UUID>","count":3}'
```

## Tests

```bash
pytest -q
```
