from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from planner_agent.document_context import build_source_context_from_pdf_dir
from web.backend.models import ApiKey, BookJob, User, UserConfig
from web.backend.schemas import BookRequest, PipelineConfig
from web.backend.security import decrypt_secret
from web.backend.web_pipeline import checkpoint_label, detect_resume_checkpoint


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "runs"
REMOVED_GOOGLE_MODELS = {
    "gemma-3-27b-it": "gemini-2.5-flash-lite",
}


def default_config() -> dict:
    return PipelineConfig().model_dump()


def get_or_create_user_config(db: Session, user: User) -> UserConfig:
    config = user.config
    if config is None:
        config = UserConfig(user_id=user.id, settings=default_config())
        db.add(config)
        db.commit()
        db.refresh(config)
    else:
        merged = {**default_config(), **(config.settings or {})}
        writer_model = str(merged.get("writer_google_model") or "")
        if writer_model in REMOVED_GOOGLE_MODELS:
            merged["writer_google_model"] = REMOVED_GOOGLE_MODELS[writer_model]
        if merged != config.settings:
            config.settings = merged
            db.add(config)
            db.commit()
            db.refresh(config)
    return config


def launch_job(db: Session, *, user: User, request: BookRequest, user_pdf_dir: Path | None = None) -> BookJob:
    config = get_or_create_user_config(db, user)
    config_payload = PipelineConfig.model_validate(config.settings or {}).model_dump()
    _validate_required_keys(db, user=user, config=config_payload, has_user_pdfs=user_pdf_dir is not None, force_web=request.force_web_research)
    planner_payload = _book_request_to_planner_input(request, user_pdf_dir=user_pdf_dir)

    stages = _initial_stages()
    job = BookJob(
        user_id=user.id,
        status="queued",
        current_stage="queued",
        request_payload=planner_payload,
        config_snapshot=config_payload,
        stages=stages,
        summary={},
        warnings={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    run_dir = RUNS_DIR / f"web_job_{job.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    job.run_dir = str(run_dir)
    db.add(job)
    db.commit()
    db.refresh(job)

    env = _build_job_environment(db, user=user, config=config_payload, request=request, user_pdf_dir=user_pdf_dir)
    env["WRITERLM_WEB_JOB_ID"] = str(job.id)
    env["WRITERLM_WEB_USER_ID"] = str(user.id)

    command = [
        sys.executable,
        "-m",
        "web.backend.pipeline_worker",
        "--job-id",
        str(job.id),
    ]
    worker_log = run_dir / "worker.log"
    with worker_log.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    job.process_id = process.pid
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def launch_retry_job(db: Session, *, user: User, source_job: BookJob) -> BookJob:
    if source_job.user_id != user.id:
        raise ValueError("Cannot retry another user's job.")
    if not source_job.run_dir:
        raise ValueError("This job has no run directory to resume from.")

    source_run_dir = Path(source_job.run_dir)
    checkpoint = detect_resume_checkpoint(source_run_dir)
    if checkpoint is None:
        raise ValueError("No resumable checkpoint was found for this job.")

    config = get_or_create_user_config(db, user)
    config_payload = PipelineConfig.model_validate({**default_config(), **(config.settings or {})}).model_dump()
    _validate_required_keys(
        db,
        user=user,
        config=config_payload,
        has_user_pdfs=False,
        force_web=bool((source_job.request_payload or {}).get("force_web_research")),
    )

    stages = _initial_stages()
    job = BookJob(
        user_id=user.id,
        status="queued",
        current_stage="queued",
        request_payload=dict(source_job.request_payload or {}),
        config_snapshot={
            **config_payload,
            "retry_of_job_id": source_job.id,
            "resume_checkpoint": checkpoint,
            "resume_from_run_dir": str(source_run_dir),
        },
        stages=stages,
        summary={
            "retry_of_job_id": source_job.id,
            "resume_checkpoint": checkpoint,
            "resume_checkpoint_label": checkpoint_label(checkpoint),
        },
        warnings={},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    run_dir = RUNS_DIR / f"web_job_{job.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    job.run_dir = str(run_dir)
    db.add(job)
    db.commit()
    db.refresh(job)

    env = _build_job_environment(db, user=user, config=config_payload)
    env["WRITERLM_WEB_JOB_ID"] = str(job.id)
    env["WRITERLM_WEB_USER_ID"] = str(user.id)
    env["WRITERLM_RESUME_FROM_RUN_DIR"] = str(source_run_dir)

    command = [
        sys.executable,
        "-m",
        "web.backend.pipeline_worker",
        "--job-id",
        str(job.id),
    ]
    worker_log = run_dir / "worker.log"
    with worker_log.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    job.process_id = process.pid
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _book_request_to_planner_input(request: BookRequest, *, user_pdf_dir: Path | None = None) -> dict:
    payload = {
        "topic": request.topic,
        "audience": request.audience,
        "tone": request.tone,
        "book_type": request.book_type,
        "theory_practice_balance": request.theory_practice_balance,
        "pedagogy_style": request.pedagogy_style,
        "source_usage": request.source_usage,
        "exercise_strategy": request.exercise_strategy,
        "goals": [goal.strip() for goal in request.goals if goal.strip()],
        "project_based": request.project_based,
        "running_project_description": request.running_project_description,
        "max_section_words": request.max_section_words,
        "content_density": {
            "code_density": request.code_density,
            "example_density": request.example_density,
            "diagram_density": request.diagram_density,
        },
        "force_web_research": request.force_web_research,
        "urls": request.urls,
        "target_quality_score": request.target_quality_score,
        "max_repair_passes": request.max_repair_passes,
        "hard_fail_threshold": request.hard_fail_threshold,
        "auto_repair": request.auto_repair,
        "sample_first": request.sample_first or request.quality_mode == "sample_first",
        "quality_mode": request.quality_mode,
    }
    if request.language_request:
        payload["language_request"] = request.language_request
    source_context = build_source_context_from_pdf_dir(user_pdf_dir)
    if source_context is not None:
        payload["source_context"] = source_context.model_dump(mode="json")

    # Apply deterministic normalization and include the generation contract
    from web.backend.normalization import normalize_book_request
    normalized = normalize_book_request(payload, original_prompt="")
    # Propagate normalized top-level fields back
    payload["code_density"] = normalized.get("code_density", payload.get("code_density"))
    payload["content_density"]["code_density"] = payload["code_density"]
    if "diagram_density" in normalized:
        payload["content_density"]["diagram_density"] = normalized["diagram_density"]
    for key in ("target_quality_score", "auto_repair", "sample_first", "quality_mode", "urls"):
        if key in normalized:
            payload[key] = normalized[key]
    # Always include generation_contract in the planner input
    payload["generation_contract"] = normalized.get("generation_contract", {})

    return payload


def _build_job_environment(
    db: Session,
    *,
    user: User,
    config: dict,
    request: BookRequest | None = None,
    user_pdf_dir: Path | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    api_keys = _api_keys_by_provider(db, user=user)
    _remove_deployment_provider_secrets(env)

    key_env_map = {
        "google": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
        "tavily": "TAVILY_API_KEY",
        "firecrawl": "FIRECRAWL_API_KEY",
    }
    for provider, env_name in key_env_map.items():
        value = api_keys.get(provider)
        if value:
            env[env_name] = value

    env.update(
        {
            "LLM_PROVIDER": config["llm_provider"],
            "PLANNER_GOOGLE_MODEL": config["planner_google_model"],
            "RESEARCHER_GOOGLE_MODEL": config["researcher_google_model"],
            "NOTES_GOOGLE_MODEL": config["notes_google_model"],
            "WRITER_GOOGLE_MODEL": config["writer_google_model"],
            "REVIEWER_GOOGLE_MODEL": config["reviewer_google_model"],
            "PLANNER_GROQ_MODEL": config["planner_groq_model"],
            "RESEARCHER_GROQ_MODEL": config["researcher_groq_model"],
            "NOTES_GROQ_MODEL": config["notes_groq_model"],
            "WRITER_GROQ_MODEL": config["writer_groq_model"],
            "REVIEWER_GROQ_MODEL": config["reviewer_groq_model"],
            "WRITERLM_PARALLEL_SECTION_PIPELINE": _bool_env(config["parallel_section_pipeline"]),
            "WRITERLM_SECTION_PIPELINE_CONCURRENCY": str(config["section_pipeline_concurrency"]),
            "WRITERLM_COMPILE_LATEX": _bool_env(config["compile_latex"]),
            "WRITERLM_STRICT_LATEX_COMPILE": _bool_env(config["strict_latex_compile"]),
            "LATEX_ENGINE": config["latex_engine"],
            "RESEARCH_EXECUTION_PROFILE": config["research_execution_profile"],
            "WRITERLM_IMAGE_ASSETS_ENABLED": _bool_env(config["image_assets_enabled"]),
            "WRITERLM_WEB_IMAGE_SEARCH_ENABLED": _bool_env(config["web_image_search_enabled"]),
            "WRITERLM_GENERATED_IMAGES_ENABLED": _bool_env(config["generated_images_enabled"]),
            "WRITERLM_IMAGE_MODEL": config["image_generation_model"],
            "WRITERLM_MAX_IMAGE_ASSETS": str(config["max_image_assets"]),
            "WRITERLM_STRICT_FULL_QA": "1",
            "WRITERLM_TARGET_QUALITY_SCORE": str(request.target_quality_score if request else 75),
            "WRITERLM_MAX_REPAIR_PASSES": str(request.max_repair_passes if request else 2),
            "WRITERLM_HARD_FAIL_THRESHOLD": str(request.hard_fail_threshold if request else 45),
            "WRITERLM_AUTO_REPAIR": _bool_env(request.auto_repair if request else True),
            "WRITERLM_SAMPLE_FIRST": _bool_env((request.sample_first or request.quality_mode == "sample_first") if request else False),
        }
    )

    env.pop("WRITERLM_TOKEN_BUDGET", None)
    env.pop("LLM_TOKEN_BUDGET", None)
    if config.get("max_completion_tokens"):
        env["WRITERLM_MAX_COMPLETION_TOKENS"] = str(config["max_completion_tokens"])

    # PDF upload support
    if user_pdf_dir is not None and user_pdf_dir.exists():
        env["WRITERLM_USER_PDF_DIR"] = str(user_pdf_dir)
    if request is not None and request.force_web_research:
        env["WRITERLM_FORCE_WEB_RESEARCH"] = "1"

    return env


def _remove_deployment_provider_secrets(env: dict[str, str]) -> None:
    for name in (
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
        "GOOGLE_AI_API_KEY",
        "GOOGLE_AI_STUDIO_API_KEY",
        "GROQ_API_KEY",
        "TAVILY_API_KEY",
        "FIRECRAWL_API_KEY",
        "FIRECRAWL_KEY",
        "NEON_DATABASE_URL",
        "WRITERLM_USER_NEON_DATABASE_URL",
    ):
        env.pop(name, None)


def _validate_required_keys(
    db: Session,
    *,
    user: User,
    config: dict,
    has_user_pdfs: bool = False,
    force_web: bool = False,
) -> None:
    api_keys = _api_keys_by_provider(db, user=user)
    missing = []
    # Tavily is only required when web research will actually run
    web_research_needed = (not has_user_pdfs) or force_web
    if web_research_needed and "tavily" not in api_keys:
        missing.append("Tavily")
    if config["llm_provider"] == "google" and "google" not in api_keys:
        missing.append("Google/Gemini")
    if config["llm_provider"] == "groq" and "groq" not in api_keys:
        missing.append("Groq")
    if missing:
        raise ValueError("Missing required API keys: " + ", ".join(missing))


def _api_keys_by_provider(db: Session, *, user: User) -> dict[str, str]:
    rows = db.query(ApiKey).filter(ApiKey.user_id == user.id).all()
    values: dict[str, str] = {}
    for row in rows:
        try:
            values[row.provider] = decrypt_secret(row.encrypted_value)
        except Exception:
            continue
    return values


def _bool_env(value: bool) -> str:
    return "1" if value else "0"


def _initial_stages() -> dict:
    return {
        name: {
            "label": label,
            "status": "queued",
            "started_at": None,
            "completed_at": None,
            "seconds": None,
            "details": {},
        }
        for name, label in [
            ("planner_research", "Planner + Researcher"),
            ("pre_run_quality", "Pre-run Quality Estimate"),
            ("sample_validation", "Sample Validation"),
            ("notes_synthesis", "Notes Synthesis"),
            ("writer", "Writer"),
            ("reviewer", "Reviewer"),
            ("quality_checker", "Quality Checker"),
            ("repair", "Repair"),
            ("image_assets", "Image Assets"),
            ("assembler", "Assembler"),
            ("latex_compile", "LaTeX Compiler"),
        ]
    }
