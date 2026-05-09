from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


ProgressCallback = Callable[[str, str], None]


RESUME_CHECKPOINTS = {
    "book_plan": ("book_plan.json", "book.json"),
    "research_bundle": ("research_bundle.json",),
    "notes_bundle": ("notes_bundle.json",),
    "writer_bundle": ("writer_bundle.json",),
    "review_bundle": ("review_bundle.json",),
    "book_tex": ("book.tex",),
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def detect_resume_checkpoint(run_dir: Path) -> str | None:
    if (run_dir / "book.tex").exists():
        return "book_tex"
    if (run_dir / "review_bundle.json").exists():
        return "review_bundle"
    if (run_dir / "writer_bundle.json").exists() and (run_dir / "notes_bundle.json").exists():
        return "writer_bundle"
    if (run_dir / "notes_bundle.json").exists():
        return "notes_bundle"
    if (run_dir / "research_bundle.json").exists():
        return "research_bundle"
    if (run_dir / "book_plan.json").exists() or (run_dir / "book.json").exists():
        return "book_plan"
    return None


def checkpoint_label(checkpoint: str | None) -> str:
    labels = {
        "book_plan": "book plan",
        "research_bundle": "research bundle",
        "notes_bundle": "notes bundle",
        "writer_bundle": "writer bundle",
        "review_bundle": "review bundle",
        "book_tex": "LaTeX manuscript",
    }
    return labels.get(checkpoint or "", "no checkpoint")


def run_web_pipeline(
    *,
    planner_input: dict[str, Any],
    run_dir: Path,
    progress: Callable[..., None],
    resume_from_dir: Path | None = None,
) -> dict[str, Any]:
    from assembler.compiler import compile_latex_file
    from assembler.image_assets import prepare_image_assets_for_review_bundle
    from assembler.io import (
        save_assembly_bundle,
        save_book_plan,
        save_latex_compile_result,
        save_latex_manuscript,
    )
    from assembler.orchestrator import run_assembler
    from llm_metrics import configure_llm_metrics, get_llm_metrics_summary
    from notes_synthesizer.llm import GroqStructuredLLM as NotesGroqStructuredLLM
    from notes_synthesizer.schemas import NotesSynthesisBundle
    from orchestration.evaluate_latex_book import evaluate_latex_book, write_outputs as write_evaluation_outputs
    from orchestration.continuity_section_pipeline import run_continuity_section_pipeline
    from orchestration.parallel_section_pipeline import ParallelSectionPipelineConfig, run_parallel_section_pipeline
    from orchestration.planner_research_pipeline import BookResearchBundle, PlannerResearchPipeline
    from orchestration.run_full_pipeline import (
        NOTES_DEFAULT_MODELS,
        WRITER_DEFAULT_MODELS,
        build_researcher_workflow,
        full_profile_enabled,
        latex_compile_enabled,
        parallel_section_pipeline_enabled,
        run_notes_layer,
        run_writer_layer,
        strict_latex_compile_enabled,
    )
    from llm_provider import get_legacy_model_env_names_by_provider, resolve_openai_compatible_config
    from planner_agent import PlannerWorkflow
    from planner_agent.schemas import BookPlan
    from reviewer.io import build_reviewer_tasks, save_review_bundle
    from reviewer.llm_client import build_reviewer_llm_client
    from reviewer.orchestrator import run_reviewer
    from reviewer.schemas import ReviewBundle
    from writer.llm import GroqStructuredLLM as WriterGroqStructuredLLM
    from writer.schemas import WriterOutputBundle
    from quality.book_contract import BookContract, classify_book_contract
    from quality.repair_loop import run_quality_repair_loop
    from quality.validator_registry import select_validators

    start_time = time.time()
    run_dir.mkdir(parents=True, exist_ok=True)
    configure_llm_metrics(path=run_dir / "llm_metrics.jsonl", reset=True)

    book_plan_path = run_dir / "book_plan.json"
    canonical_book_path = run_dir / "book.json"
    research_bundle_path = run_dir / "research_bundle.json"
    notes_bundle_path = run_dir / "notes_bundle.json"
    writer_bundle_path = run_dir / "writer_bundle.json"
    review_bundle_path = run_dir / "review_bundle.json"
    image_assets_path = run_dir / "image_assets.json"
    book_state_path = run_dir / "book_state.json"
    section_summary_path = run_dir / "section_pipeline_summary.json"
    assembly_bundle_path = run_dir / "assembly_bundle.json"
    latex_path = run_dir / "book.tex"
    latex_build_dir = run_dir / "latex_build"
    latex_compile_result_path = run_dir / "latex_compile_result.json"
    evaluation_json_path = run_dir / "book_evaluation.json"
    evaluation_md_path = run_dir / "book_evaluation.md"
    run_summary_path = run_dir / "run_summary.json"

    stage_timings: dict[str, float] = {}
    resume_checkpoint = detect_resume_checkpoint(resume_from_dir) if resume_from_dir else None
    if (
        resume_from_dir
        and resume_checkpoint in {"notes_bundle", "writer_bundle", "review_bundle"}
        and full_profile_enabled()
        and not (resume_from_dir / "book_state.json").exists()
        and (resume_from_dir / "research_bundle.json").exists()
    ):
        resume_checkpoint = "research_bundle"
    resume_details = (
        {"resumed_from": str(resume_from_dir), "checkpoint": checkpoint_label(resume_checkpoint)}
        if resume_from_dir and resume_checkpoint
        else None
    )

    book_plan = None
    research_bundle = None
    research_bundle_payload = None
    notes_bundle = None
    writer_bundle = None
    review_bundle = None
    section_pipeline_summary: dict[str, Any] = {}

    if resume_from_dir and not resume_checkpoint:
        raise RuntimeError(f"No resumable checkpoint found in {resume_from_dir}")

    if resume_checkpoint == "book_tex":
        source_book_plan_path = resume_from_dir / "book_plan.json"
        if not source_book_plan_path.exists():
            source_book_plan_path = resume_from_dir / "book.json"
        if source_book_plan_path.exists():
            book_plan = BookPlan.model_validate(load_json(source_book_plan_path))
            save_book_plan(book_plan, book_plan_path)
            save_book_plan(book_plan, canonical_book_path)
        latex_path.write_text((resume_from_dir / "book.tex").read_text(encoding="utf-8"), encoding="utf-8")
        for stage in ("planner_research", "notes_synthesis", "writer", "reviewer", "quality_checker", "image_assets", "assembler"):
            progress(stage, "completed", details=resume_details)

    elif resume_checkpoint == "review_bundle":
        review_bundle = ReviewBundle.model_validate(load_json(resume_from_dir / "review_bundle.json"))
        save_review_bundle(review_bundle, review_bundle_path)
        source_book_plan_path = resume_from_dir / "book_plan.json"
        if not source_book_plan_path.exists():
            source_book_plan_path = resume_from_dir / "book.json"
        book_plan = BookPlan.model_validate(load_json(source_book_plan_path))
        save_book_plan(book_plan, book_plan_path)
        save_book_plan(book_plan, canonical_book_path)
        for stage in ("planner_research", "notes_synthesis", "writer", "reviewer"):
            progress(stage, "completed", details=resume_details)

    elif resume_checkpoint == "writer_bundle":
        notes_bundle = NotesSynthesisBundle.model_validate(load_json(resume_from_dir / "notes_bundle.json"))
        writer_bundle = WriterOutputBundle.model_validate(load_json(resume_from_dir / "writer_bundle.json"))
        write_json(notes_bundle_path, notes_bundle.model_dump(mode="json"))
        write_json(writer_bundle_path, writer_bundle.model_dump(mode="json"))
        source_book_plan_path = resume_from_dir / "book_plan.json"
        if not source_book_plan_path.exists():
            source_book_plan_path = resume_from_dir / "book.json"
        book_plan = BookPlan.model_validate(load_json(source_book_plan_path))
        save_book_plan(book_plan, book_plan_path)
        save_book_plan(book_plan, canonical_book_path)
        for stage in ("planner_research", "notes_synthesis", "writer"):
            progress(stage, "completed", details=resume_details)

    elif resume_checkpoint == "notes_bundle":
        notes_bundle = NotesSynthesisBundle.model_validate(load_json(resume_from_dir / "notes_bundle.json"))
        write_json(notes_bundle_path, notes_bundle.model_dump(mode="json"))
        source_book_plan_path = resume_from_dir / "book_plan.json"
        if not source_book_plan_path.exists():
            source_book_plan_path = resume_from_dir / "book.json"
        book_plan = BookPlan.model_validate(load_json(source_book_plan_path))
        save_book_plan(book_plan, book_plan_path)
        save_book_plan(book_plan, canonical_book_path)
        for stage in ("planner_research", "notes_synthesis"):
            progress(stage, "completed", details=resume_details)

    elif resume_checkpoint == "research_bundle":
        research_bundle_payload = load_json(resume_from_dir / "research_bundle.json")
        research_bundle = BookResearchBundle.model_validate(research_bundle_payload)
        book_plan = research_bundle.book_plan
        save_book_plan(book_plan, book_plan_path)
        save_book_plan(book_plan, canonical_book_path)
        write_json(research_bundle_path, research_bundle_payload)
        progress("planner_research", "completed", details={
            **(resume_details or {}),
            "chapters": book_plan.get_chapter_count(),
            "researched_sections": sum(len(ch.section_packets) for ch in research_bundle.chapters),
            "warnings": len(research_bundle.warnings),
            "errors": len(research_bundle.errors),
        })

    elif resume_checkpoint == "book_plan":
        source_book_plan_path = resume_from_dir / "book_plan.json"
        if not source_book_plan_path.exists():
            source_book_plan_path = resume_from_dir / "book.json"
        book_plan = BookPlan.model_validate(load_json(source_book_plan_path))
        save_book_plan(book_plan, book_plan_path)
        save_book_plan(book_plan, canonical_book_path)

    if research_bundle_payload is None and resume_from_dir and (resume_from_dir / "research_bundle.json").exists():
        research_bundle_payload = load_json(resume_from_dir / "research_bundle.json")
        write_json(research_bundle_path, research_bundle_payload)
        if research_bundle is None:
            research_bundle = BookResearchBundle.model_validate(research_bundle_payload)
    if resume_from_dir and (resume_from_dir / "book_state.json").exists():
        book_state_path.write_text((resume_from_dir / "book_state.json").read_text(encoding="utf-8"), encoding="utf-8")

    if (
        research_bundle_payload is None
        and notes_bundle is None
        and writer_bundle is None
        and review_bundle is None
        and latex_path.exists() is False
    ):
        progress("planner_research", "running", details=resume_details)
        stage_start = time.perf_counter()
        planner_workflow = PlannerWorkflow()
        researcher_workflow = build_researcher_workflow()
        pipeline = PlannerResearchPipeline(
            planner_workflow=planner_workflow,
            researcher_workflow=researcher_workflow,
        )
        research_bundle = pipeline.run_from_book_plan(book_plan) if book_plan is not None else pipeline.run(planner_input)
        stage_timings["planner_research"] = round(time.perf_counter() - stage_start, 2)
        book_plan = research_bundle.book_plan
        save_book_plan(book_plan, book_plan_path)
        save_book_plan(book_plan, canonical_book_path)
        research_bundle_payload = research_bundle.model_dump(mode="json")
        write_json(research_bundle_path, research_bundle_payload)
        progress(
            "planner_research",
            "completed",
            seconds=stage_timings["planner_research"],
            details={
                "chapters": book_plan.get_chapter_count(),
                "researched_sections": sum(len(ch.section_packets) for ch in research_bundle.chapters),
                "warnings": len(research_bundle.warnings),
                "errors": len(research_bundle.errors),
            },
        )

    if review_bundle is not None:
        section_pipeline_summary = {
            "mode": "resume_from_review_bundle",
            "failed_sections": 0,
            "checkpoint": checkpoint_label(resume_checkpoint),
        }
    elif writer_bundle is not None and notes_bundle is not None:
        progress("reviewer", "running", details=resume_details)
        reviewer_tasks = build_reviewer_tasks(
            notes_bundle=notes_bundle,
            writer_bundle=writer_bundle,
        )
        stage_start = time.perf_counter()
        review_bundle = run_reviewer(tasks=reviewer_tasks, llm_client=build_reviewer_llm_client())
        stage_timings["reviewer"] = round(time.perf_counter() - stage_start, 2)
        progress("reviewer", "completed", seconds=stage_timings["reviewer"])
        section_pipeline_summary = {"mode": "resume_from_writer_bundle", "failed_sections": 0}
    elif notes_bundle is not None:
        progress("writer", "running", details=resume_details)
        stage_start = time.perf_counter()
        writer_state = run_writer_layer(
            notes_bundle_payload=notes_bundle.model_dump(mode="json"),
            book_title=book_plan.title,
            run_id=run_dir.name,
        )
        stage_timings["writer"] = round(time.perf_counter() - stage_start, 2)
        progress("writer", "completed", seconds=stage_timings["writer"])

        writer_bundle = writer_state.output_bundle
        if writer_bundle is None:
            raise RuntimeError("Writer completed without an output bundle.")

        progress("reviewer", "running")
        reviewer_tasks = build_reviewer_tasks(
            notes_bundle=notes_bundle,
            writer_bundle=writer_bundle,
        )
        stage_start = time.perf_counter()
        review_bundle = run_reviewer(tasks=reviewer_tasks, llm_client=build_reviewer_llm_client())
        stage_timings["reviewer"] = round(time.perf_counter() - stage_start, 2)
        progress("reviewer", "completed", seconds=stage_timings["reviewer"])
        section_pipeline_summary = {"mode": "resume_from_notes_bundle", "failed_sections": 0}
    elif full_profile_enabled():
        notes_llm_config = resolve_openai_compatible_config(
            layer="notes",
            default_models=NOTES_DEFAULT_MODELS,
            legacy_env_names_by_provider=get_legacy_model_env_names_by_provider(),
        )
        writer_llm_config = resolve_openai_compatible_config(
            layer="writer",
            default_models=WRITER_DEFAULT_MODELS,
            legacy_env_names_by_provider=get_legacy_model_env_names_by_provider(),
        )
        progress("notes_synthesis", "running")
        progress("writer", "running")
        progress("reviewer", "running")
        stage_start = time.perf_counter()
        section_pipeline_result = run_continuity_section_pipeline(
            research_bundle_payload=research_bundle_payload,
            planner_input=planner_input,
            book_plan=book_plan,
            book_title=book_plan.title,
            run_id=run_dir.name,
            run_dir=run_dir,
            notes_llm_factory=lambda: NotesGroqStructuredLLM(
                api_key=notes_llm_config.api_key,
                model=notes_llm_config.model,
                base_url=notes_llm_config.base_url,
            ),
            writer_llm_factory=lambda: WriterGroqStructuredLLM(
                api_key=writer_llm_config.api_key,
                model=writer_llm_config.model,
                base_url=writer_llm_config.base_url,
            ),
            reviewer_llm_client_factory=build_reviewer_llm_client,
            config=ParallelSectionPipelineConfig(max_workers=1),
        )
        section_seconds = round(time.perf_counter() - stage_start, 2)
        stage_timings["continuity_section_pipeline"] = section_seconds
        notes_state = section_pipeline_result.notes_state
        writer_state = section_pipeline_result.writer_state
        review_bundle = section_pipeline_result.review_bundle
        section_pipeline_summary = section_pipeline_result.summary
        shared_details = {
            "mode": section_pipeline_summary.get("mode"),
            "completed_sections": section_pipeline_summary.get("completed_sections"),
            "failed_sections": section_pipeline_summary.get("failed_sections"),
            "book_state_path": str(section_pipeline_result.book_state_path) if section_pipeline_result.book_state_path else None,
        }
        final_status = "failed" if section_pipeline_summary.get("failed_sections") else "completed"
        progress("notes_synthesis", final_status, seconds=section_seconds, details=shared_details)
        progress("writer", final_status, seconds=section_seconds, details=shared_details)
        progress("reviewer", final_status, seconds=section_seconds, details=shared_details)
        notes_bundle = section_pipeline_result.notes_state.output_bundle
        writer_bundle = section_pipeline_result.writer_state.output_bundle
    elif parallel_section_pipeline_enabled():
        notes_llm_config = resolve_openai_compatible_config(
            layer="notes",
            default_models=NOTES_DEFAULT_MODELS,
            legacy_env_names_by_provider=get_legacy_model_env_names_by_provider(),
        )
        writer_llm_config = resolve_openai_compatible_config(
            layer="writer",
            default_models=WRITER_DEFAULT_MODELS,
            legacy_env_names_by_provider=get_legacy_model_env_names_by_provider(),
        )
        progress("notes_synthesis", "running")
        progress("writer", "running")
        progress("reviewer", "running")
        stage_start = time.perf_counter()
        section_pipeline_result = run_parallel_section_pipeline(
            research_bundle_payload=research_bundle_payload,
            book_title=book_plan.title,
            run_id=run_dir.name,
            notes_llm_factory=lambda: NotesGroqStructuredLLM(
                api_key=notes_llm_config.api_key,
                model=notes_llm_config.model,
                base_url=notes_llm_config.base_url,
            ),
            writer_llm_factory=lambda: WriterGroqStructuredLLM(
                api_key=writer_llm_config.api_key,
                model=writer_llm_config.model,
                base_url=writer_llm_config.base_url,
            ),
            reviewer_llm_client_factory=build_reviewer_llm_client,
            config=ParallelSectionPipelineConfig.from_env(),
        )
        section_seconds = round(time.perf_counter() - stage_start, 2)
        stage_timings["parallel_section_pipeline"] = section_seconds
        notes_state = section_pipeline_result.notes_state
        writer_state = section_pipeline_result.writer_state
        review_bundle = section_pipeline_result.review_bundle
        section_pipeline_summary = section_pipeline_result.summary
        shared_details = {
            "mode": section_pipeline_summary.get("mode"),
            "completed_sections": section_pipeline_summary.get("completed_sections"),
            "failed_sections": section_pipeline_summary.get("failed_sections"),
        }
        final_status = "failed" if section_pipeline_summary.get("failed_sections") else "completed"
        progress("notes_synthesis", final_status, seconds=section_seconds, details=shared_details)
        progress("writer", final_status, seconds=section_seconds, details=shared_details)
        progress("reviewer", final_status, seconds=section_seconds, details=shared_details)
        notes_bundle = section_pipeline_result.notes_state.output_bundle
        writer_bundle = section_pipeline_result.writer_state.output_bundle
    else:
        progress("notes_synthesis", "running")
        stage_start = time.perf_counter()
        notes_state = run_notes_layer(
            research_bundle_payload=research_bundle_payload,
            book_title=book_plan.title,
            run_id=run_dir.name,
        )
        stage_timings["notes_synthesis"] = round(time.perf_counter() - stage_start, 2)
        progress("notes_synthesis", "completed", seconds=stage_timings["notes_synthesis"])

        notes_bundle_for_writer = notes_state.output_bundle
        if notes_bundle_for_writer is None:
            raise RuntimeError("Notes layer completed without an output bundle.")

        progress("writer", "running")
        stage_start = time.perf_counter()
        writer_state = run_writer_layer(
            notes_bundle_payload=notes_bundle_for_writer.model_dump(mode="json"),
            book_title=book_plan.title,
            run_id=run_dir.name,
        )
        stage_timings["writer"] = round(time.perf_counter() - stage_start, 2)
        progress("writer", "completed", seconds=stage_timings["writer"])

        writer_bundle_for_review = writer_state.output_bundle
        if writer_bundle_for_review is None:
            raise RuntimeError("Writer completed without an output bundle.")

        progress("reviewer", "running")
        reviewer_tasks = build_reviewer_tasks(
            notes_bundle=notes_bundle_for_writer,
            writer_bundle=writer_bundle_for_review,
        )
        stage_start = time.perf_counter()
        review_bundle = run_reviewer(tasks=reviewer_tasks, llm_client=build_reviewer_llm_client())
        stage_timings["reviewer"] = round(time.perf_counter() - stage_start, 2)
        progress("reviewer", "completed", seconds=stage_timings["reviewer"])
        section_pipeline_summary = {"mode": "sequential_layer_pipeline", "failed_sections": 0}
        notes_bundle = notes_bundle_for_writer
        writer_bundle = writer_bundle_for_review

    write_json(section_summary_path, section_pipeline_summary)

    if review_bundle is None:
        raise RuntimeError("Section pipeline did not produce a review bundle.")
    if notes_bundle is not None and writer_bundle is not None:
        write_json(notes_bundle_path, notes_bundle.model_dump(mode="json"))
        write_json(writer_bundle_path, writer_bundle.model_dump(mode="json"))
    elif notes_bundle is not None or writer_bundle is not None:
        raise RuntimeError("Section pipeline produced an incomplete notes/writer checkpoint.")
    save_review_bundle(review_bundle, review_bundle_path)

    failed_section_count = int(section_pipeline_summary.get("failed_sections") or 0)
    if failed_section_count:
        failed_section_ids = section_pipeline_summary.get("failed_section_ids") or []
        raise RuntimeError(f"Section pipeline failed before assembly: {failed_section_ids}")

    progress("quality_checker", "running")
    stage_start = time.perf_counter()
    
    book_contract = None
    if research_bundle_payload and "book_contract" in research_bundle_payload:
        book_contract = BookContract.model_validate(research_bundle_payload["book_contract"])
    else:
        book_contract = classify_book_contract(planner_input, book_plan)
        validator_activations = select_validators(book_contract)
        book_contract.activated_validators = [item.name for item in validator_activations]
        book_contract.validator_rationales = {item.name: item.reason for item in validator_activations}
        write_json(run_dir / "book_contract.json", book_contract.model_dump(mode="json"))
        if research_bundle_payload:
            research_bundle_payload["book_contract"] = book_contract.model_dump(mode="json")
            write_json(research_bundle_path, research_bundle_payload)

    repair_result = run_quality_repair_loop(
        review_bundle=review_bundle,
        contract=book_contract,
    )
    review_bundle = repair_result.review_bundle
    stage_timings["quality_checker"] = round(time.perf_counter() - stage_start, 2)
    save_review_bundle(review_bundle, review_bundle_path)
    qa_report_path = run_dir / "qa_report.json"
    write_json(qa_report_path, repair_result.qa_report)
    
    progress(
        "quality_checker", 
        "completed", 
        seconds=stage_timings["quality_checker"],
        details={
            "qa_score": repair_result.qa_report.get("overall_score"),
            "issues_fixed": repair_result.qa_report.get("issues_fixed", 0)
        }
    )

    progress("image_assets", "running")
    stage_start = time.perf_counter()
    image_asset_result = prepare_image_assets_for_review_bundle(
        review_bundle=review_bundle,
        run_dir=run_dir,
        book_title=book_plan.title,
    )
    stage_timings["image_assets"] = round(time.perf_counter() - stage_start, 2)
    save_review_bundle(review_bundle, review_bundle_path)
    progress(
        "image_assets",
        "completed",
        seconds=stage_timings["image_assets"],
        details={
            "enabled": image_asset_result.enabled,
            "created": len(image_asset_result.created),
            "warnings": len(image_asset_result.warnings),
        },
    )

    progress("assembler", "running")
    stage_start = time.perf_counter()
    # Use the book_plan already resolved during this job's pipeline run.
    # DO NOT call resolve_book_plan_for_review() here — that function does a glob
    # search across all runs/* directories and will find stale book_plan.json files
    # from previous jobs, causing an "overlap mismatch" assembler failure.
    assembler_book_plan = book_plan
    save_book_plan(assembler_book_plan, canonical_book_path)
    assembly_artifacts = run_assembler(
        book_plan=assembler_book_plan,
        review_bundle=review_bundle,
        book_plan_path=canonical_book_path,
        review_bundle_path=review_bundle_path,
        latex_output_path=latex_path,
    )
    stage_timings["assembler"] = round(time.perf_counter() - stage_start, 2)
    save_assembly_bundle(assembly_artifacts.assembly_bundle, assembly_bundle_path)
    save_latex_manuscript(assembly_artifacts.latex_manuscript, latex_path)
    progress(
        "assembler",
        "completed",
        seconds=stage_timings["assembler"],
        details={
            "status": assembly_artifacts.assembly_bundle.metadata.assembly_status.value,
            "assembled_sections": assembly_artifacts.assembly_bundle.metadata.assembled_section_count,
            "flagged_sections": assembly_artifacts.assembly_bundle.metadata.flagged_sections,
        },
    )

    latex_compile_result = None
    if latex_compile_enabled():
        progress("latex_compile", "running")
        stage_start = time.perf_counter()
        latex_compile_result = compile_latex_file(
            latex_path,
            build_dir=latex_build_dir,
            output_pdf_name=book_plan.title,
        )
        stage_timings["latex_compile"] = round(time.perf_counter() - stage_start, 2)
        save_latex_compile_result(latex_compile_result, latex_compile_result_path)
        latex_status = "completed" if latex_compile_result.succeeded else "failed"
        latex_issues = sorted(
            latex_compile_result.issues,
            key=lambda issue: 0 if issue.severity == "error" else 1,
        )
        progress(
            "latex_compile",
            latex_status,
            seconds=stage_timings["latex_compile"],
            details={
                "status": latex_compile_result.status,
                "pdf_path": latex_compile_result.pdf_path,
                "issues": [f"{issue.severity}: {issue.message}" for issue in latex_issues[:5]],
            },
        )
        if strict_latex_compile_enabled() and not latex_compile_result.succeeded:
            first_issue = latex_compile_result.issues[0].message if latex_compile_result.issues else "Unknown LaTeX compile failure."
            raise RuntimeError(f"LaTeX compilation failed: {first_issue}")
    else:
        progress("latex_compile", "completed", details={"status": "disabled"})

    evaluation = evaluate_latex_book(latex_path)
    write_evaluation_outputs(evaluation, evaluation_json_path, evaluation_md_path)

    llm_usage = get_llm_metrics_summary()
    book_status = (
        "completed"
        if latex_compile_result is None or latex_compile_result.succeeded
        else "completed_with_latex_issue"
    )
    artifacts = {
        "book_plan": str(book_plan_path),
        "research_bundle": str(research_bundle_path),
        "notes_bundle": str(notes_bundle_path),
        "writer_bundle": str(writer_bundle_path),
        "review_bundle": str(review_bundle_path),
        "image_assets": str(image_assets_path),
        "book_state": str(book_state_path) if book_state_path.exists() else None,
        "section_pipeline_summary": str(section_summary_path),
        "assembly_bundle": str(assembly_bundle_path),
        "latex": str(latex_path),
        "latex_compile_result": str(latex_compile_result_path) if latex_compile_result else None,
        "pdf": latex_compile_result.pdf_path if latex_compile_result and latex_compile_result.pdf_path else None,
        "book_evaluation": str(evaluation_md_path),
        "llm_metrics": str(run_dir / "llm_metrics.jsonl"),
    }
    summary = {
        "elapsed_seconds": round(time.time() - start_time, 2),
        "stage_timings": stage_timings,
        "section_pipeline": section_pipeline_summary,
        "llm_usage": llm_usage,
        "evaluation": {
            "quality_score": evaluation["quality_score"],
            "totals": evaluation["totals"],
            "weak_section_count": evaluation["weak_section_count"],
            "recommendations": evaluation["recommendations"],
        },
        "latex_compile": latex_compile_result.model_dump() if latex_compile_result else None,
    }
    write_json(run_summary_path, {**summary, "artifacts": artifacts})
    return {
        "title": book_plan.title,
        "book_status": book_status,
        "summary": summary,
        "warnings": {
            "research": research_bundle.warnings if research_bundle is not None else [],
            "research_errors": research_bundle.errors if research_bundle is not None else [],
        },
        "artifacts": artifacts,
    }
