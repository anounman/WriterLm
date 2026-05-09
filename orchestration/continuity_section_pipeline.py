from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import time

from notes_synthesizer.llm import GroqStructuredLLM as NotesGroqStructuredLLM
from notes_synthesizer.state import NotesSynthesizerSectionTask
from orchestration.book_state import (
    BookState,
    build_initial_book_state,
    build_section_context,
    update_book_state_from_reviewed_section,
    write_book_state,
)
from orchestration.parallel_section_pipeline import (
    ParallelSectionPipelineConfig,
    ParallelSectionPipelineResult,
    SectionPipelineJobResult,
    _build_notes_state,
    _build_pipeline_summary,
    _build_review_bundle,
    _build_writer_state,
    _format_task_error,
    _resolve_stage_client,
    _run_single_notes_task,
    _run_single_reviewer_task,
    _run_single_writer_task,
)
from orchestration.run_notes_synthesizer import build_tasks_from_research_bundle
from planner_agent.schemas import BookPlan
from reviewer.node import LLMClientProtocol
from writer.llm import GroqStructuredLLM as WriterGroqStructuredLLM


@dataclass
class ContinuitySectionPipelineResult(ParallelSectionPipelineResult):
    book_state: BookState
    book_state_path: Path | None = None


def run_continuity_section_pipeline(
    *,
    research_bundle_payload: dict[str, Any],
    planner_input: dict[str, Any],
    book_plan: BookPlan,
    book_title: str,
    run_id: str,
    run_dir: Path | None = None,
    notes_llm: NotesGroqStructuredLLM | None = None,
    writer_llm: WriterGroqStructuredLLM | None = None,
    reviewer_llm_client: LLMClientProtocol | None = None,
    notes_llm_factory: Callable[[], NotesGroqStructuredLLM] | None = None,
    writer_llm_factory: Callable[[], WriterGroqStructuredLLM] | None = None,
    reviewer_llm_client_factory: Callable[[], LLMClientProtocol] | None = None,
    config: ParallelSectionPipelineConfig | None = None,
) -> ContinuitySectionPipelineResult:
    config = config or ParallelSectionPipelineConfig.from_env()
    book_state = build_initial_book_state(
        book_plan=book_plan,
        planner_input=planner_input,
        research_bundle_payload=research_bundle_payload,
    )

    tasks = build_tasks_from_research_bundle(
        research_bundle_payload,
        book_state={},
    )
    if not tasks:
        raise RuntimeError("No section tasks could be built from the research bundle.")

    results: list[SectionPipelineJobResult] = []
    for order_index, task in enumerate(tasks):
        contextualized_task = _attach_book_state(task, book_state)
        result = _run_one_continuity_section(
            order_index=order_index,
            notes_task=contextualized_task,
            book_title=book_title,
            run_id=run_id,
            notes_llm=notes_llm,
            writer_llm=writer_llm,
            reviewer_llm_client=reviewer_llm_client,
            notes_llm_factory=notes_llm_factory,
            writer_llm_factory=writer_llm_factory,
            reviewer_llm_client_factory=reviewer_llm_client_factory,
        )
        results.append(result)
        if result.reviewer_task is not None and result.reviewer_task.section_output is not None:
            book_state = update_book_state_from_reviewed_section(
                book_state=book_state,
                section_id=result.section_id,
                section_title=result.section_title,
                reviewed_content=result.reviewer_task.section_output.reviewed_content,
                citations_used=result.reviewer_task.section_output.citations_used,
            )
            if run_dir is not None:
                write_book_state(run_dir / "book_state.json", book_state)

    notes_state = _build_notes_state(
        run_id=run_id,
        book_title=book_title,
        original_tasks=tasks,
        results=results,
    )
    writer_state = _build_writer_state(
        run_id=run_id,
        book_title=book_title,
        results=results,
    )
    review_bundle = _build_review_bundle(results)
    summary = _build_pipeline_summary(max_workers=1, results=results)
    summary["mode"] = "continuity_section_pipeline"
    summary["book_state_sections"] = len(book_state.section_history)
    summary["book_state_path"] = str(run_dir / "book_state.json") if run_dir is not None else None

    return ContinuitySectionPipelineResult(
        notes_state=notes_state,
        writer_state=writer_state,
        review_bundle=review_bundle,
        summary=summary,
        book_state=book_state,
        book_state_path=(run_dir / "book_state.json") if run_dir is not None else None,
    )


def _attach_book_state(task: NotesSynthesizerSectionTask, book_state: BookState) -> NotesSynthesizerSectionTask:
    planner_section = dict(task.planner_section_ref or {})
    chapter_title = str(planner_section.get("chapter_title") or "")
    planner_section["book_state"] = build_section_context(
        book_state=book_state,
        section_id=task.section_id,
        section_title=task.section_title,
        chapter_title=chapter_title,
    )
    if book_state.book_contract is not None:
        planner_section["book_contract"] = book_state.book_contract.model_dump(mode="json")
    task.planner_section_ref = planner_section
    return task


def _run_one_continuity_section(
    *,
    order_index: int,
    notes_task: NotesSynthesizerSectionTask,
    book_title: str,
    run_id: str,
    notes_llm: NotesGroqStructuredLLM | None,
    writer_llm: WriterGroqStructuredLLM | None,
    reviewer_llm_client: LLMClientProtocol | None,
    notes_llm_factory: Callable[[], NotesGroqStructuredLLM] | None = None,
    writer_llm_factory: Callable[[], WriterGroqStructuredLLM] | None = None,
    reviewer_llm_client_factory: Callable[[], LLMClientProtocol] | None = None,
) -> SectionPipelineJobResult:
    result = SectionPipelineJobResult(
        order_index=order_index,
        section_id=notes_task.section_id,
        section_title=notes_task.section_title,
        timings={},
    )

    section_notes_llm = _resolve_stage_client(client=notes_llm, factory=notes_llm_factory, stage_name="notes")
    section_writer_llm = _resolve_stage_client(client=writer_llm, factory=writer_llm_factory, stage_name="writer")
    section_reviewer_llm_client = _resolve_stage_client(
        client=reviewer_llm_client,
        factory=reviewer_llm_client_factory,
        stage_name="reviewer",
    )

    stage_start = time.perf_counter()
    notes_result = _run_single_notes_task(
        task=notes_task,
        book_title=book_title,
        run_id=run_id,
        llm=section_notes_llm,
    )
    result.timings["notes"] = round(time.perf_counter() - stage_start, 2)
    result.notes_task = notes_result
    note = notes_result.synthesized_note
    if note is None:
        result.error_message = _format_task_error(notes_result, "notes")
        return result

    stage_start = time.perf_counter()
    writer_result = _run_single_writer_task(
        note=note,
        book_title=book_title,
        run_id=run_id,
        llm=section_writer_llm,
    )
    result.timings["writer"] = round(time.perf_counter() - stage_start, 2)
    result.writer_task = writer_result
    draft = writer_result.draft
    if draft is None:
        result.error_message = _format_task_error(writer_result, "writer")
        return result

    stage_start = time.perf_counter()
    reviewer_result = _run_single_reviewer_task(
        note=note,
        draft=draft,
        llm_client=section_reviewer_llm_client,
    )
    result.timings["reviewer"] = round(time.perf_counter() - stage_start, 2)
    result.reviewer_task = reviewer_result
    if reviewer_result.section_output is None:
        result.error_message = reviewer_result.error_message or "reviewer failed"
    return result
