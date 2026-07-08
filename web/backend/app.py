from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
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
    JobArtifactOut,
    JobOut,
    PipelineConfig,
    ProviderModelOut,
    QualityEstimateRequest,
    RepairRequest,
    RepairResponseOut,
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

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env.backend"))
except Exception:
    pass

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

ACTIVE_JOB_STATUSES = {"queued", "running", "validating", "repairing"}
TERMINAL_JOB_STATUSES = {
    "completed",
    "completed_with_latex_issue",
    "completed_with_warnings",
    "completed_with_major_issues",
    "qa_failed",
    "needs_user_review",
    "failed",
    "stopped",
}
SUPPORTED_API_KEY_PROVIDERS = {"google", "groq", "ollama", "tavily", "firecrawl"}
STALE_PROCESS_MESSAGES = {
    "Job process is no longer running.",
    "Job process exited unexpectedly. Check worker.log for details.",
    "Job worker exited before starting. Check worker.log for details.",
}
JOB_ARTIFACT_FILES = {
    "worker_log": "worker.log",
    "job_error": "job_error.txt",
    "book": "book.json",
    "bookstate": "book_state.json",
    "book_state": "book_state.json",
    "researchbundle": "research_bundle.json",
    "research_bundle": "research_bundle.json",
    "bookplan": "book_plan.json",
    "book_plan": "book_plan.json",
    "telemetry": "telemetry.json",
    "qa_report": "qa_report.json",
    "quality_timeline": "quality_timeline.json",
    "repair_history": "repair_history.json",
    "weak_sections": "weak_sections.json",
    "showcase_readiness": "showcase_readiness.json",
    "latex": "book.tex",
}


def _safe_pdf_filename(filename: str | None) -> str:
    original = Path(filename or "source.pdf").name
    stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in Path(original).stem)
    stem = stem.strip("._")[:80] or "source"
    return f"{stem}_{uuid.uuid4().hex[:8]}.pdf"


def _safe_download_filename(value: str | None, *, extension: str) -> str:
    stem = (value or "").strip()
    if extension and stem.lower().endswith(extension.lower()):
        stem = stem[: -len(extension)]
    stem = unicodedata.normalize("NFKC", stem)
    stem = re.sub(r"[^\w .-]+", "", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._-")
    if not stem:
        stem = "book"
    return f"{stem[:120]}{extension}"


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


def _run_repair_action(
    db: Session,
    *,
    user: User,
    job_id: int,
    action: str,
    payload: RepairRequest | None,
) -> dict:
    from planner_agent.schemas import BookPlan
    from quality.book_contract import BookContract, classify_book_contract
    from quality.control import (
        QualityGateConfig,
        build_quality_checkpoint,
        qa_score,
        quality_label,
        quality_status_for_score,
        score_breakdown,
        showcase_readiness,
        summarize_top_issues,
        weak_sections,
    )
    from quality.repair_loop import run_quality_repair_loop
    from reviewer.io import save_review_bundle
    from reviewer.schemas import ReviewBundle
    from assembler.compiler import compile_latex_file
    from assembler.io import save_assembly_bundle, save_latex_compile_result, save_latex_manuscript
    from assembler.orchestrator import run_assembler

    job = db.query(BookJob).filter(BookJob.user_id == user.id, BookJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.run_dir:
        raise HTTPException(status_code=400, detail="This job does not have a run directory.")
    if job.status in {"queued", "running", "validating", "repairing"}:
        raise HTTPException(status_code=400, detail="Wait for the current generation step to finish before repairing.")

    run_dir = Path(job.run_dir)
    review_path = run_dir / "review_bundle.json"
    if not review_path.exists():
        raise HTTPException(status_code=404, detail="No review bundle is available to repair.")

    old_status = job.status
    repair_mode = action
    started_at = _utciso()
    stages = dict(job.stages or {})
    repair_stage = dict(stages.get("repair") or {})
    repair_stage.setdefault("label", "Repair")
    repair_stage["status"] = "running"
    repair_stage["started_at"] = started_at
    repair_stage["completed_at"] = None
    repair_stage["details"] = {**(repair_stage.get("details") or {}), "action": repair_mode}
    stages["repair"] = repair_stage
    job.stages = stages
    job.status = "repairing"
    job.current_stage = "repair"
    db.add(job)
    db.commit()
    db.refresh(job)

    previous_report = None
    try:
        review_bundle = ReviewBundle.model_validate(json.loads(review_path.read_text(encoding="utf-8")))
        contract_path = run_dir / "book_contract.json"
        if contract_path.exists():
            book_contract = BookContract.model_validate(json.loads(contract_path.read_text(encoding="utf-8")))
        else:
            book_plan_path = run_dir / "book_plan.json"
            book_plan = BookPlan.model_validate(json.loads(book_plan_path.read_text(encoding="utf-8"))) if book_plan_path.exists() else None
            book_contract = classify_book_contract(job.request_payload or {}, book_plan)

        config_payload = dict(job.request_payload or {})
        if payload and payload.target_quality_score is not None:
            config_payload["target_quality_score"] = payload.target_quality_score
        if payload and payload.max_repair_passes is not None:
            config_payload["max_repair_passes"] = payload.max_repair_passes
        config = QualityGateConfig.from_payload(config_payload)

        qa_path = run_dir / "qa_report.json"
        if qa_path.exists():
            previous_report = json.loads(qa_path.read_text(encoding="utf-8"))
        previous_score = qa_score(previous_report)

        target_section_ids: set[str] | None = None
        if repair_mode == "weak_sections":
            weak_path = run_dir / "weak_sections.json"
            if weak_path.exists():
                weak_payload = json.loads(weak_path.read_text(encoding="utf-8"))
                target_section_ids = {
                    str(item.get("section_id"))
                    for item in (weak_payload.get("sections") or [])
                    if item.get("section_id")
                }

        result = run_quality_repair_loop(
            review_bundle=review_bundle,
            contract=book_contract,
            max_passes=max(1, config.max_repair_passes),
            repair_mode=repair_mode,
            target_section_ids=target_section_ids,
        )
        save_review_bundle(result.review_bundle, review_path)
        score = qa_score(result.qa_report)
        qa_passed = bool(result.qa_report.get("qa_passed", True))
        qa_report = {
            **result.qa_report,
            "overall_score": score,
            "quality_label": quality_label(score),
            "score_breakdown": score_breakdown(result.qa_report),
            "top_issues": summarize_top_issues(result.qa_report),
            "last_repair_action": repair_mode,
            "repair_started_at": started_at,
        }
        qa_path.write_text(json.dumps(qa_report, indent=2, ensure_ascii=False), encoding="utf-8")

        history_path = run_dir / "repair_history.json"
        history = {"passes": []}
        if history_path.exists():
            history = json.loads(history_path.read_text(encoding="utf-8"))
        history_entry = {
            "action": repair_mode,
            "started_at": started_at,
            "finished_at": _utciso(),
            "previous_score": previous_score,
            "new_score": score,
            "status": "completed",
            "issues_before": summarize_top_issues(previous_report) if previous_report else [],
            "issues_after": summarize_top_issues(qa_report),
            "artifacts_updated": True,
            "error": None,
        }
        history["passes"] = [*(history.get("passes") or []), history_entry]
        history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

        timeline_path = run_dir / "quality_timeline.json"
        timeline = []
        if timeline_path.exists():
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        timeline.append(
            build_quality_checkpoint(
                stage=f"repair:{repair_mode}",
                qa_report=qa_report,
                action="completed",
                config=config,
            )
        )
        timeline_path.write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")

        weak = weak_sections(qa_report)
        (run_dir / "weak_sections.json").write_text(json.dumps({"sections": weak}, indent=2, ensure_ascii=False), encoding="utf-8")
        showcase = showcase_readiness(qa_report, config)
        (run_dir / "showcase_readiness.json").write_text(json.dumps(showcase, indent=2, ensure_ascii=False), encoding="utf-8")

        book_plan_path = run_dir / "book_plan.json"
        if not book_plan_path.exists():
            book_plan_path = run_dir / "book.json"
        if not book_plan_path.exists():
            raise RuntimeError("Book plan is missing; cannot rebuild artifacts after repair.")
        book_plan = BookPlan.model_validate(json.loads(book_plan_path.read_text(encoding="utf-8")))

        assembly_bundle_path = run_dir / "assembly_bundle.json"
        latex_path = run_dir / "book.tex"
        latex_build_dir = run_dir / "latex_build"
        latex_compile_result_path = run_dir / "latex_compile_result.json"

        assembly_artifacts = run_assembler(
            book_plan=book_plan,
            review_bundle=result.review_bundle,
            book_plan_path=book_plan_path,
            review_bundle_path=review_path,
            latex_output_path=latex_path,
        )
        save_assembly_bundle(assembly_artifacts.assembly_bundle, assembly_bundle_path)
        save_latex_manuscript(assembly_artifacts.latex_manuscript, latex_path)

        latex_compile_result = None
        config_snapshot = dict(job.config_snapshot or {})
        compile_latex = bool(config_snapshot.get("compile_latex", True))
        strict_latex = bool(config_snapshot.get("strict_latex_compile", False))
        latex_engine = str(config_snapshot.get("latex_engine") or "pdflatex")
        if compile_latex:
            latex_compile_result = compile_latex_file(
                latex_path,
                build_dir=latex_build_dir,
                preferred_engine=latex_engine,
                output_pdf_name=book_plan.title,
            )
            save_latex_compile_result(latex_compile_result, latex_compile_result_path)

        next_status = quality_status_for_score(score, config, qa_passed=qa_passed)
        latex_error_message = None
        if latex_compile_result is not None and not latex_compile_result.succeeded:
            first_issue = latex_compile_result.issues[0].message if latex_compile_result.issues else "Unknown LaTeX compile failure."
            latex_error_message = f"LaTeX compilation failed: {first_issue}"
            if strict_latex:
                next_status = "completed_with_latex_issue"
            elif next_status == "completed":
                next_status = "completed_with_warnings"
        summary = dict(job.summary or {})
        summary["repair"] = {
            "action": repair_mode,
            "status": "completed",
            "started_at": started_at,
            "finished_at": _utciso(),
            "previous_score": previous_score,
            "new_score": score,
            "passes": len(history.get("passes") or []),
        }
        summary["quality"] = {
            **(summary.get("quality") or {}),
            "score": score,
            "label": quality_label(score),
            "status": next_status,
            "breakdown": score_breakdown(qa_report),
            "top_issues": summarize_top_issues(qa_report),
            "repair_passes": len(history.get("passes") or []),
            "weak_section_count": len(weak),
            "showcase_ready": showcase["ready"],
            "last_repair_action": repair_mode,
            "last_repair_started_at": started_at,
            "last_repair_finished_at": _utciso(),
        }
        job.status = next_status
        job.current_stage = "completed"
        job.summary = summary
        job.error_message = latex_error_message
        job.completed_at = datetime.now(timezone.utc)
        stages = dict(job.stages or {})
        repair_stage = dict(stages.get("repair") or {})
        repair_stage["status"] = "completed"
        repair_stage["completed_at"] = _utciso()
        repair_stage["details"] = {**(repair_stage.get("details") or {}), "result": next_status}
        stages["repair"] = repair_stage
        job.stages = stages
        if job.book is not None:
            job.book.status = next_status
            job.book.summary_metrics = summary
            job.book.latex_path = str(latex_path)
            job.book.pdf_path = latex_compile_result.pdf_path if latex_compile_result and latex_compile_result.pdf_path else job.book.pdf_path
            job.book.artifact_paths = {
                **(job.book.artifact_paths or {}),
                "review_bundle": str(review_path),
                "qa_report": str(qa_path),
                "quality_timeline": str(timeline_path),
                "repair_history": str(history_path),
                "weak_sections": str(run_dir / "weak_sections.json"),
                "showcase_readiness": str(run_dir / "showcase_readiness.json"),
                "assembly_bundle": str(assembly_bundle_path),
                "latex": str(latex_path),
                "latex_compile_result": str(latex_compile_result_path) if latex_compile_result else None,
                "pdf": latex_compile_result.pdf_path if latex_compile_result and latex_compile_result.pdf_path else None,
            }
            db.add(job.book)
        db.add(job)
        db.commit()
        db.refresh(job)
        artifacts = _collect_job_artifacts(job)
        return {
            "job": job,
            "repair": {
                "action": repair_mode,
                "status": "completed",
                "started_at": started_at,
                "finished_at": _utciso(),
                "previous_score": previous_score,
                "new_score": score,
                "qa_passed": qa_passed,
                "artifacts_updated": True,
                "artifacts": artifacts,
                "message": f"Repair completed for {repair_mode}.",
            },
        }
    except Exception as exc:
        logger.exception("Repair failed for job %s", job.id)
        history_path = run_dir / "repair_history.json"
        history = {"passes": []}
        if history_path.exists():
            history = json.loads(history_path.read_text(encoding="utf-8"))
        history_entry = {
            "action": repair_mode,
            "started_at": started_at,
            "finished_at": _utciso(),
            "previous_score": qa_score(previous_report),
            "new_score": None,
            "status": "failed",
            "issues_before": summarize_top_issues(previous_report) if previous_report else [],
            "issues_after": [],
            "artifacts_updated": False,
            "error": str(exc),
        }
        history["passes"] = [*(history.get("passes") or []), history_entry]
        history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

        stages = dict(job.stages or {})
        repair_stage = dict(stages.get("repair") or {})
        repair_stage["status"] = "failed"
        repair_stage["completed_at"] = _utciso()
        repair_stage["details"] = {**(repair_stage.get("details") or {}), "error": str(exc)}
        stages["repair"] = repair_stage
        job.stages = stages
        job.status = old_status
        job.current_stage = "completed"
        job.error_message = f"Repair failed: {exc}"
        db.add(job)
        db.commit()
        db.refresh(job)
        raise HTTPException(status_code=500, detail=job.error_message) from exc


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


def _find_latest_pdf(build_dir: Path) -> Path | None:
    if not build_dir.exists() or not build_dir.is_dir():
        return None
    candidates = sorted(build_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _resolve_job_artifact_path(job: BookJob, artifact_key: str) -> Path:
    if not job.run_dir:
        raise HTTPException(status_code=404, detail="This job does not have a run directory yet.")
    run_dir = Path(job.run_dir).resolve()
    path: Path | None = None

    filename = JOB_ARTIFACT_FILES.get(artifact_key)
    if filename is not None:
        path = (run_dir / filename).resolve()
    elif artifact_key == "pdf":
        if job.book and job.book.pdf_path:
            path = Path(job.book.pdf_path).resolve()
        else:
            path = _find_latest_pdf(run_dir / "latex_build")
            if path:
                path = path.resolve()
    elif artifact_key == "latex":
        if job.book and job.book.latex_path:
            path = Path(job.book.latex_path).resolve()
        else:
            path = (run_dir / "book.tex").resolve()

    if path is None:
        raise HTTPException(status_code=404, detail="Artifact is not available for download.")
    if run_dir not in path.parents and path != run_dir:
        raise HTTPException(status_code=403, detail="Artifact path is outside the run directory.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file is missing.")
    return path


def _try_resolve_job_artifact(job: BookJob, artifact_key: str) -> Path | None:
    try:
        return _resolve_job_artifact_path(job, artifact_key)
    except HTTPException:
        return None


def _collect_job_artifacts(job: BookJob) -> list[JobArtifactOut]:
    if not job.run_dir:
        return []
    artifacts: list[JobArtifactOut] = []
    seen: set[Path] = set()
    keys = list(JOB_ARTIFACT_FILES.keys()) + ["pdf"]
    for key in keys:
        if key in {"book_state", "research_bundle", "book_plan"}:
            continue
        path = _try_resolve_job_artifact(job, key)
        if not path or path in seen:
            continue
        seen.add(path)
        stat = path.stat()
        artifacts.append(
            JobArtifactOut(
                key=key,
                filename=path.name,
                size_bytes=stat.st_size,
                updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            )
        )
    return artifacts


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


def _model_label(model_id: str) -> str:
    return model_id.removeprefix("models/")


def _fetch_google_models(api_key: str) -> list[ProviderModelOut]:
    try:
        response = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Google model list could not be loaded. Check your Google API key.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Google model list could not be loaded right now.") from exc

    models = []
    for item in response.json().get("models", []):
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        methods = set(item.get("supportedGenerationMethods") or [])
        if methods and "generateContent" not in methods:
            continue
        model_id = name.removeprefix("models/")
        models.append(ProviderModelOut(id=model_id, label=str(item.get("displayName") or _model_label(model_id))))
    return sorted(models, key=lambda model: model.id)


def _fetch_groq_models(api_key: str) -> list[ProviderModelOut]:
    try:
        response = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Groq model list could not be loaded. Check your Groq API key.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Groq model list could not be loaded right now.") from exc

    models = []
    for item in response.json().get("data", []):
        model_id = str(item.get("id") or "").strip()
        if model_id:
            models.append(ProviderModelOut(id=model_id, label=model_id))
    return sorted(models, key=lambda model: model.id)


def _fetch_ollama_models(api_key: str | None) -> list[ProviderModelOut]:
    from llm_provider import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_LOCAL_BASE_URL

    if api_key:
        url = f"{DEFAULT_OLLAMA_BASE_URL}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        error_hint = "Check your Ollama API key."
    else:
        url = f"{DEFAULT_OLLAMA_LOCAL_BASE_URL}/models"
        headers = {}
        error_hint = "Is a local Ollama daemon running (ollama serve)?"

    try:
        response = httpx.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama model list could not be loaded. {error_hint}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama model list could not be loaded right now. {error_hint}") from exc

    models = []
    for item in response.json().get("data", []):
        model_id = str(item.get("id") or "").strip()
        if model_id:
            models.append(ProviderModelOut(id=model_id, label=model_id))
    return sorted(models, key=lambda model: model.id)


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


@app.get("/models/{provider}", response_model=list[ProviderModelOut])
def list_provider_models(provider: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ProviderModelOut]:
    if provider not in {"google", "groq", "ollama"}:
        raise HTTPException(status_code=404, detail="Provider does not expose LLM models.")
    api_key = _api_keys_by_provider(db, user=user).get(provider)
    if provider == "ollama":
        # Local daemon needs no key; only cloud (ollama.com) does.
        return _fetch_ollama_models(api_key)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"Save a {provider.title()} API key before loading models.")
    if provider == "google":
        return _fetch_google_models(api_key)
    return _fetch_groq_models(api_key)


import logging
logger = logging.getLogger(__name__)

class ParsePromptRequest(BaseModel):
    prompt: str


@app.post("/jobs/parse-prompt")
def parse_prompt(payload: ParsePromptRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from web.backend.llm_util import parse_user_prompt
    try:
        return parse_user_prompt(db, user, payload.prompt)
    except Exception as exc:
        logger.exception("Failed to parse prompt")
        raise HTTPException(status_code=400, detail={"detail": str(exc), "message": "Failed to parse prompt. See backend logs for details."}) from exc


@app.post("/jobs/quality-estimate")
def estimate_job_quality(payload: QualityEstimateRequest, user: User = Depends(current_user)) -> dict:
    from quality.control import estimate_quality_risk
    from web.backend.pipeline_jobs import _book_request_to_planner_input

    return estimate_quality_risk(_book_request_to_planner_input(payload.request))


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
    if source_job.status not in {"failed", "stopped", "completed_with_latex_issue", "qa_failed", "needs_user_review", "completed_with_major_issues", "completed_with_warnings"}:
        raise HTTPException(status_code=400, detail="Only failed, stopped, warning, or quality-issue jobs can be retried.")
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


@app.post("/jobs/{job_id}/repair", response_model=RepairResponseOut)
def repair_job(job_id: int, payload: RepairRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _run_repair_action(db, user=user, job_id=job_id, action="general", payload=payload)


@app.post("/jobs/{job_id}/repair/code", response_model=RepairResponseOut)
def repair_job_code(job_id: int, payload: RepairRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _run_repair_action(db, user=user, job_id=job_id, action="code", payload=payload)


@app.post("/jobs/{job_id}/repair/diagrams", response_model=RepairResponseOut)
def repair_job_diagrams(job_id: int, payload: RepairRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _run_repair_action(db, user=user, job_id=job_id, action="diagrams", payload=payload)


@app.post("/jobs/{job_id}/repair/sources", response_model=RepairResponseOut)
def repair_job_sources(job_id: int, payload: RepairRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _run_repair_action(db, user=user, job_id=job_id, action="sources", payload=payload)


@app.post("/jobs/{job_id}/repair/showcase", response_model=RepairResponseOut)
def repair_job_showcase(job_id: int, payload: RepairRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _run_repair_action(db, user=user, job_id=job_id, action="showcase", payload=payload)


@app.post("/jobs/{job_id}/repair/weak-sections", response_model=RepairResponseOut)
def repair_job_weak_sections(job_id: int, payload: RepairRequest | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _run_repair_action(db, user=user, job_id=job_id, action="weak_sections", payload=payload)


@app.get("/jobs/{job_id}/artifacts", response_model=list[JobArtifactOut])
def list_job_artifacts(job_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[JobArtifactOut]:
    job = db.query(BookJob).filter(BookJob.user_id == user.id, BookJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _collect_job_artifacts(job)


@app.get("/jobs/{job_id}/artifacts/{artifact_key}")
def download_job_artifact(
    job_id: int,
    artifact_key: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    job = db.query(BookJob).filter(BookJob.user_id == user.id, BookJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    path = _resolve_job_artifact_path(job, artifact_key)
    return FileResponse(path, filename=path.name)


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
    download_filename = path.name
    if artifact_name == "pdf":
        download_filename = _safe_download_filename(book.title, extension=".pdf")
    elif artifact_name == "latex":
        download_filename = _safe_download_filename(book.title, extension=".tex")
    return FileResponse(path, filename=download_filename)
