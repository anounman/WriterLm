from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from web.backend.database import get_db, init_db
from web.backend.deps import current_user
from web.backend.models import ApiKey, BookJob, GeneratedBook, User
from web.backend.pipeline_jobs import default_config, get_or_create_user_config, launch_job, launch_retry_job
from web.backend.schemas import (
    ApiKeyOut,
    ApiKeyUpsert,
    BookRequest,
    GeneratedBookOut,
    JobOut,
    PipelineConfig,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserOut,
)
from web.backend.security import (
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    password_hash,
    secret_fingerprint,
    verify_password,
)


app = FastAPI(title="WriterLM Studio API", version="0.1.0")

origins = [
    origin.strip()
    for origin in os.getenv("APP_CORS_ORIGINS", "http://localhost:5173,http://localhost:8080,https://writelm.anounman.de").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACTIVE_JOB_STATUSES = {"queued", "running"}
TERMINAL_JOB_STATUSES = {"completed", "completed_with_latex_issue", "failed", "stopped"}
SUPPORTED_API_KEY_PROVIDERS = {"google", "groq", "tavily", "firecrawl"}
STALE_PROCESS_MESSAGES = {
    "Job process is no longer running.",
    "Job process exited unexpectedly. Check worker.log for details.",
    "Job worker exited before starting. Check worker.log for details.",
}


def _safe_pdf_filename(filename: str | None) -> str:
    original = Path(filename or "source.pdf").name
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in Path(original).stem)
    stem = stem.strip("._")[:80] or "source"
    return f"{stem}_{uuid.uuid4().hex[:8]}.pdf"


def _utciso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_is_alive(pid: int | None) -> bool:
    if not pid:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    try:
        stat = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "stat="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        ).strip()
    except Exception:
        return True
    return bool(stat) and not stat.startswith("Z")


def _mark_job_stopped(db: Session, job: BookJob, message: str = "Job was stopped.") -> BookJob:
    now = datetime.now(timezone.utc)
    stages = dict(job.stages or {})
    active_stage = job.current_stage

    for stage_name, entry in list(stages.items()):
        stage_entry = dict(entry or {})
        if stage_entry.get("status") == "running" or stage_name == active_stage:
            if stage_entry.get("status") != "completed":
                stage_entry["status"] = "stopped"
                stage_entry["completed_at"] = _utciso()
                stage_entry["details"] = {
                    **(stage_entry.get("details") or {}),
                    "message": message,
                }
                stages[stage_name] = stage_entry

    job.status = "stopped"
    job.current_stage = "stopped"
    job.completed_at = now
    job.error_message = message
    job.stages = stages
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _mark_job_failed(db: Session, job: BookJob, message: str) -> BookJob:
    now = datetime.now(timezone.utc)
    stages = dict(job.stages or {})
    active_stage = job.current_stage

    for stage_name, entry in list(stages.items()):
        stage_entry = dict(entry or {})
        if stage_entry.get("status") == "running" or stage_name == active_stage:
            if stage_entry.get("status") != "completed":
                stage_entry["status"] = "failed"
                stage_entry["completed_at"] = _utciso()
                stage_entry["details"] = {
                    **(stage_entry.get("details") or {}),
                    "message": message,
                }
                stages[stage_name] = stage_entry

    job.status = "failed"
    job.current_stage = "failed"
    job.completed_at = now
    job.error_message = message
    job.stages = stages
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _has_running_stage(job: BookJob) -> bool:
    return any((entry or {}).get("status") == "running" for entry in (job.stages or {}).values())


def _read_worker_state(job: BookJob) -> dict | None:
    if not job.run_dir:
        return None
    try:
        state_path = Path(job.run_dir) / "worker_state.json"
        if not state_path.exists():
            return None
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if state.get("job_id") != job.id:
        return None
    return state


def _restore_live_job(db: Session, job: BookJob, *, stage: str | None = None) -> BookJob:
    stages = dict(job.stages or {})
    job.status = "running"
    running_stage = stage or next(
        (stage_name for stage_name, entry in stages.items() if (entry or {}).get("status") == "running"),
        None,
    )
    if running_stage:
        job.current_stage = running_stage
        stage_entry = dict(stages.get(running_stage) or {})
        stage_entry.setdefault("label", running_stage.replace("_", " ").title())
        stage_entry["status"] = "running"
        stage_entry.setdefault("started_at", _utciso())
        stage_entry["completed_at"] = None
        details = dict(stage_entry.get("details") or {})
        if details.get("message") in STALE_PROCESS_MESSAGES:
            details.pop("message", None)
        stage_entry["details"] = details
        stages[running_stage] = stage_entry
    job.completed_at = None
    if job.error_message in STALE_PROCESS_MESSAGES:
        job.error_message = None
    job.stages = stages
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _reconcile_job_status(db: Session, job: BookJob) -> BookJob:
    if job.status in TERMINAL_JOB_STATUSES and _has_running_stage(job) and _pid_is_alive(job.process_id):
        return _restore_live_job(db, job)
    worker_state = _read_worker_state(job)
    if (
        job.status in TERMINAL_JOB_STATUSES
        and worker_state
        and worker_state.get("status") == "running"
        and _pid_is_alive(job.process_id)
    ):
        return _restore_live_job(db, job, stage=str(worker_state.get("stage") or job.current_stage or "queued"))
    if job.status not in ACTIVE_JOB_STATUSES:
        return job
    if job.process_id and not _pid_is_alive(job.process_id):
        if job.current_stage == "queued" or job.started_at is None:
            return _mark_job_failed(db, job, "Job worker exited before starting. Check worker.log for details.")
        return _mark_job_failed(db, job, "Job process exited unexpectedly. Check worker.log for details.")
    return job


def _stop_process(pid: int | None) -> None:
    if not pid or not _pid_is_alive(pid):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return


def _safe_key_hint(row: ApiKey) -> str:
    if row.key_hint.startswith("key-") or row.key_hint == "saved":
        return row.key_hint
    return "saved"


def _normalize_api_key_hints() -> None:
    from web.backend.database import SessionLocal

    db = SessionLocal()
    try:
        rows = db.query(ApiKey).all()
        changed = False
        for row in rows:
            if row.key_hint.startswith("key-") or row.key_hint == "saved":
                continue
            try:
                row.key_hint = secret_fingerprint(decrypt_secret(row.encrypted_value))
            except Exception:
                row.key_hint = "saved"
            db.add(row)
            changed = True
        if changed:
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()
    _normalize_api_key_hints()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/signup", response_model=TokenResponse)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(email=payload.email.lower(), password_hash=password_hash(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    get_or_create_user_config(db, user)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ApiKeyOut]:
    rows = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.provider).all()
    return [
        ApiKeyOut(
            id=row.id,
            provider=row.provider,
            key_hint=_safe_key_hint(row),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
        if row.provider in SUPPORTED_API_KEY_PROVIDERS
    ]


@app.put("/api-keys/{provider}", response_model=ApiKeyOut)
def upsert_api_key(
    provider: str,
    payload: ApiKeyUpsert,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> ApiKeyOut:
    if provider not in SUPPORTED_API_KEY_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported API key provider.")
    if provider != payload.provider:
        raise HTTPException(status_code=400, detail="Provider path and payload do not match.")
    row = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.provider == provider).first()
    if row is None:
        row = ApiKey(user_id=user.id, provider=provider, encrypted_value="", key_hint="")
    row.encrypted_value = encrypt_secret(payload.value)
    row.key_hint = secret_fingerprint(payload.value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiKeyOut(id=row.id, provider=row.provider, key_hint=row.key_hint, created_at=row.created_at, updated_at=row.updated_at)


@app.delete("/api-keys/{provider}", status_code=204)
def delete_api_key(provider: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    row = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.provider == provider).first()
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


@app.get("/config", response_model=PipelineConfig)
def get_config(user: User = Depends(current_user), db: Session = Depends(get_db)) -> PipelineConfig:
    config = get_or_create_user_config(db, user)
    return PipelineConfig.model_validate({**default_config(), **(config.settings or {})})


@app.put("/config", response_model=PipelineConfig)
def update_config(payload: PipelineConfig, user: User = Depends(current_user), db: Session = Depends(get_db)) -> PipelineConfig:
    config = get_or_create_user_config(db, user)
    config.settings = payload.model_dump()
    db.add(config)
    db.commit()
    return payload


class ParsePromptRequest(BaseModel):
    prompt: str


@app.post("/jobs/parse-prompt")
def parse_prompt(payload: ParsePromptRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from web.backend.llm_util import parse_user_prompt
    try:
        return parse_user_prompt(db, user, payload.prompt)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs", response_model=JobOut)
def create_job(payload: BookRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BookJob:
    try:
        return launch_job(db, user=user, request=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs/upload", response_model=JobOut)
async def create_job_with_pdfs(
    request_json: str = Form(..., description="JSON-serialised BookRequest"),
    pdf_files: list[UploadFile] = File(default=[], description="Optional PDF source files"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> BookJob:
    """
    Create a job and optionally attach PDF source files.

    The client sends a multipart/form-data request with:
    - ``request_json``: the full BookRequest as a JSON string
    - ``pdf_files``: zero or more PDF files (optional)
    """
    try:
        request = BookRequest.model_validate_json(request_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request JSON: {exc}") from exc

    # Save uploaded PDFs to a temporary staging directory.
    # pipeline_jobs.launch_job will pass WRITERLM_USER_PDF_DIR so the
    # worker process knows where to find them.
    user_pdf_dir: Path | None = None
    invalid_files = [
        upload
        for upload in pdf_files
        if not upload.filename or not upload.filename.lower().endswith(".pdf")
    ]
    if invalid_files:
        raise HTTPException(status_code=400, detail="Only PDF files can be uploaded.")
    valid_pdfs = [upload for upload in pdf_files if upload.filename]
    if valid_pdfs:
        staging_dir = Path(os.environ.get("WRITERLM_UPLOAD_STAGING", "/tmp")) / "writerlm_pdfs" / str(uuid.uuid4())
        staging_dir.mkdir(parents=True, exist_ok=True)
        for upload in valid_pdfs:
            dest = staging_dir / _safe_pdf_filename(upload.filename)
            with dest.open("wb") as fh:
                shutil.copyfileobj(upload.file, fh)
        user_pdf_dir = staging_dir

    try:
        return launch_job(db, user=user, request=request, user_pdf_dir=user_pdf_dir)
    except ValueError as exc:
        # Clean up staging dir on validation failure
        if user_pdf_dir and user_pdf_dir.exists():
            shutil.rmtree(user_pdf_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[BookJob]:
    jobs = (
        db.query(BookJob)
        .filter(BookJob.user_id == user.id)
        .order_by(BookJob.created_at.desc())
        .limit(50)
        .all()
    )
    return [_reconcile_job_status(db, job) for job in jobs]


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BookJob:
    job = db.query(BookJob).filter(BookJob.user_id == user.id, BookJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _reconcile_job_status(db, job)


@app.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BookJob:
    source_job = db.query(BookJob).filter(BookJob.user_id == user.id, BookJob.id == job_id).first()
    if source_job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if source_job.status not in {"failed", "stopped", "completed_with_latex_issue"}:
        raise HTTPException(status_code=400, detail="Only failed, stopped, or LaTeX-issue jobs can be retried.")
    try:
        return launch_retry_job(db, user=user, source_job=source_job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/stop", response_model=JobOut)
def stop_job(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> BookJob:
    job = db.query(BookJob).filter(BookJob.user_id == user.id, BookJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status in TERMINAL_JOB_STATUSES:
        return job
    _stop_process(job.process_id)
    return _mark_job_stopped(db, job, "Job was stopped by the user.")


@app.get("/books", response_model=list[GeneratedBookOut])
def list_books(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[GeneratedBook]:
    return (
        db.query(GeneratedBook)
        .filter(GeneratedBook.user_id == user.id)
        .order_by(GeneratedBook.created_at.desc())
        .all()
    )


@app.get("/books/{book_id}", response_model=GeneratedBookOut)
def get_book(book_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> GeneratedBook:
    book = db.query(GeneratedBook).filter(GeneratedBook.user_id == user.id, GeneratedBook.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    return book


@app.get("/books/{book_id}/artifacts/{artifact_name}")
def download_artifact(
    book_id: int,
    artifact_name: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    book = db.query(GeneratedBook).filter(GeneratedBook.user_id == user.id, GeneratedBook.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found.")
    artifact_paths = book.artifact_paths or {}
    path_value = artifact_paths.get(artifact_name)
    if artifact_name == "pdf" and book.pdf_path:
        path_value = book.pdf_path
    if artifact_name == "latex" and book.latex_path:
        path_value = book.latex_path
    if not path_value:
        raise HTTPException(status_code=404, detail="Artifact not available.")
    path = Path(path_value).resolve()
    run_dir = Path(book.run_dir).resolve()
    if run_dir not in path.parents and path != run_dir:
        raise HTTPException(status_code=403, detail="Artifact path is outside the run directory.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file is missing.")
    return FileResponse(path, filename=path.name)
