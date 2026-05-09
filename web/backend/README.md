# WriterLM — Backend API

The backend is a **FastAPI** application that serves as the orchestration layer between the WriterLM Studio UI and the AI generation pipeline. It handles user authentication, encrypted API key management, job lifecycle management, and streaming pipeline output to connected clients.

---

## Architecture

```
web/backend/
├── app.py              # FastAPI application entrypoint — all REST endpoints
├── web_pipeline.py     # Pipeline orchestration: adapts the core pipeline to run as a background job
├── pipeline_worker.py  # Subprocess worker that actually executes the pipeline in isolation
├── pipeline_jobs.py    # Job creation, configuration, and retry logic
├── models.py           # SQLAlchemy ORM models (User, BookJob, ApiKey, GeneratedBook)
├── schemas.py          # Pydantic request/response models (BookRequest, JobOut, etc.)
├── database.py         # DB session and initialization
├── deps.py             # FastAPI dependencies (current_user, etc.)
├── security.py         # JWT auth, Fernet encryption for API keys, password hashing
└── llm_util.py         # LLM helper for parsing natural language prompts into book specs
```

### Key Concepts

- **Jobs**: Every book generation request creates a `BookJob` record in the database. The job is dispatched as a separate subprocess (`pipeline_worker.py`) and its status is tracked via DB updates and a `worker_state.json` file in the job's run directory.
- **API Key Encryption**: User-provided LLM and Search API keys are encrypted at rest using Fernet symmetric encryption, keyed off `APP_ENCRYPTION_KEY`. They are decrypted at job launch time and injected into the subprocess environment — they are never stored in plaintext.
- **Job Reconciliation**: The `/jobs` and `/jobs/{id}` endpoints run a reconciliation check (`_reconcile_job_status`) that cross-references the DB status against the live subprocess PID to recover from stale or crashed worker states.

---

## REST API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/signup` | Register a new user |
| `POST` | `/auth/login` | Login and receive a JWT |
| `GET` | `/me` | Get current authenticated user |
| `GET/PUT` | `/api-keys/{provider}` | Manage encrypted provider API keys |
| `GET/PUT` | `/config` | Get/update user pipeline configuration |
| `POST` | `/jobs` | Create a new book generation job |
| `POST` | `/jobs/upload` | Create a job with PDF file uploads |
| `GET` | `/jobs` | List all jobs for the user |
| `GET` | `/jobs/{id}` | Get a single job with live status |
| `POST` | `/jobs/{id}/stop` | Stop a running job |
| `POST` | `/jobs/{id}/retry` | Retry a failed/stopped job |
| `GET` | `/books` | List all completed generated books |
| `GET` | `/books/{id}/artifacts/{name}` | Download a book artifact (PDF, LaTeX) |

---

## Local Development Setup

### 1. Install Dependencies

```bash
# From the repo root
pip install -r requirements.txt
```

### 2. Environment Variables

The backend reads from `.env.backend` (or the root `.env`). The critical variables are:

```bash
DATABASE_URL=postgresql://user:password@host:port/db   # PostgreSQL connection string
APP_ENCRYPTION_KEY=<fernet-key>                        # Fernet key for encrypting user API keys
APP_CORS_ORIGINS=http://localhost:5173,http://localhost:8080
SECRET_KEY=<random-secret>                             # JWT signing key

# Generate a Fernet key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Run the Server

```bash
uvicorn web.backend.app:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.

---

## Running with Docker

From the repo root:

```bash
docker-compose up --build backend
```

---

## Database

The backend uses **SQLAlchemy** with a PostgreSQL database. Tables are created automatically on startup via `init_db()`. There are no migration scripts — schema changes require a fresh DB or manual `ALTER TABLE`.

**Models:**
- `User` — Stores email + hashed password.
- `ApiKey` — Per-user, per-provider encrypted API keys.
- `BookJob` — Tracks the full lifecycle of a generation job (status, stages, process ID, run directory).
- `GeneratedBook` — A completed book with artifact paths (LaTeX, PDF).
- `UserPipelineConfig` — Per-user pipeline settings (model choice, concurrency, etc.).
