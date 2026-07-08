from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from notes_synthesizer.graph import build_notes_synthesizer_graph, initialize_state
from notes_synthesizer.llm import GroqStructuredLLM as NotesGroqStructuredLLM
from notes_synthesizer.schemas import NotesSynthesisBundle, SectionNoteArtifact, SynthesisStatus
from notes_synthesizer.state import (
    NotesSynthesizerInput,
    NotesSynthesizerSectionTask,
    NotesSynthesizerState,
)
from orchestration.run_notes_synthesizer import build_tasks_from_research_bundle
from orchestration.run_writer import build_tasks_from_notes_bundle
from reviewer.io import build_reviewer_tasks
from reviewer.node import LLMClientProtocol, review_section_safe
from reviewer.schemas import (
    ReviewBundle,
    ReviewBundleMetadata,
    ReviewStatus,
    ReviewerSectionResult,
)
from reviewer.state import ReviewerSectionTask
from writer.graph import build_writer_graph, initialize_writer_state
from writer.llm import GroqStructuredLLM as WriterGroqStructuredLLM
from writer.schemas import SectionDraft, WriterOutputBundle, WritingStatus
from writer.state import WriterInput, WriterSectionTask, WriterState


@dataclass(frozen=True)
class ParallelSectionPipelineConfig:
    max_workers: int = 4

    @classmethod
    def from_env(cls) -> "ParallelSectionPipelineConfig":
        return cls(
            max_workers=_read_positive_int_env(
                "WRITERLM_SECTION_PIPELINE_CONCURRENCY",
                "SECTION_PIPELINE_CONCURRENCY",
                default=4,
            )
        )


@dataclass
class SectionPipelineJobResult:
    order_index: int
    section_id: str
    section_title: str
    notes_task: NotesSynthesizerSectionTask | None = None
    writer_task: WriterSectionTask | None = None
    reviewer_task: ReviewerSectionTask | None = None
    error_message: str | None = None
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.error_message is not None


@dataclass
class ParallelSectionPipelineResult:
    notes_state: NotesSynthesizerState
    writer_state: WriterState
    review_bundle: ReviewBundle
    summary: dict[str, Any]


def run_parallel_section_pipeline(
    *,
    research_bundle_payload: dict[str, Any],
    book_title: str,
    run_id: str,
    notes_llm: NotesGroqStructuredLLM | None = None,
    writer_llm: WriterGroqStructuredLLM | None = None,
    reviewer_llm_client: LLMClientProtocol | None = None,
    notes_llm_factory: Callable[[], NotesGroqStructuredLLM] | None = None,
    writer_llm_factory: Callable[[], WriterGroqStructuredLLM] | None = None,
    reviewer_llm_client_factory: Callable[[], LLMClientProtocol] | None = None,
    config: ParallelSectionPipelineConfig | None = None,
) -> ParallelSectionPipelineResult:
    """
    Run Notes -> Writer -> Reviewer per section with bounded parallelism.

    Research remains a full-stage barrier. Once the research bundle exists, each
    section can independently move through notes, writing, and review. Final
    bundles are rebuilt in the original book order.
    """
    config = config or ParallelSectionPipelineConfig.from_env()
    notes_tasks = build_tasks_from_research_bundle(research_bundle_payload)
    if not notes_tasks:
        raise RuntimeError("No section tasks could be built from the research bundle.")

    max_workers = max(config.max_workers, 1)
    results: list[SectionPipelineJobResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_one_section_pipeline,
                order_index=index,
                notes_task=task,
                book_title=book_title,
                run_id=run_id,
                notes_llm=notes_llm,
                writer_llm=writer_llm,
                reviewer_llm_client=reviewer_llm_client,
                notes_llm_factory=notes_llm_factory,
                writer_llm_factory=writer_llm_factory,
                reviewer_llm_client_factory=reviewer_llm_client_factory,
            ): (index, task)
            for index, task in enumerate(notes_tasks)
        }

        for future in as_completed(futures):
            order_index, task = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    SectionPipelineJobResult(
                        order_index=order_index,
                        section_id=task.section_id,
                        section_title=task.section_title,
                        notes_task=task,
                        error_message=str(exc),
                    )
                )

    ordered_results = sorted(results, key=lambda item: item.order_index)
    notes_state = _build_notes_state(
        run_id=run_id,
        book_title=book_title,
        original_tasks=notes_tasks,
        results=ordered_results,
    )
    writer_state = _build_writer_state(
        run_id=run_id,
        book_title=book_title,
        results=ordered_results,
    )
    review_bundle = _build_review_bundle(ordered_results)

    return ParallelSectionPipelineResult(
        notes_state=notes_state,
        writer_state=writer_state,
        review_bundle=review_bundle,
        summary=_build_pipeline_summary(
            max_workers=max_workers,
            results=ordered_results,
        ),
    )


def _run_one_section_pipeline(
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
    timings: dict[str, float] = {}
    result = SectionPipelineJobResult(
        order_index=order_index,
        section_id=notes_task.section_id,
        section_title=notes_task.section_title,
        timings=timings,
    )

    section_notes_llm = _resolve_stage_client(
        client=notes_llm,
        factory=notes_llm_factory,
        stage_name="notes",
    )
    section_writer_llm = _resolve_stage_client(
        client=writer_llm,
        factory=writer_llm_factory,
        stage_name="writer",
    )
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
    timings["notes"] = round(time.perf_counter() - stage_start, 2)
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
    timings["writer"] = round(time.perf_counter() - stage_start, 2)
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
    timings["reviewer"] = round(time.perf_counter() - stage_start, 2)
    result.reviewer_task = reviewer_result

    if reviewer_result.section_output is None:
        result.error_message = reviewer_result.error_message or "Reviewer failed."

    return result


def _resolve_stage_client(
    *,
    client: Any | None,
    factory: Callable[[], Any] | None,
    stage_name: str,
) -> Any:
    if factory is not None:
        return factory()
    if client is not None:
        return client
    raise RuntimeError(f"No {stage_name} LLM client or client factory was provided.")


def _run_single_notes_task(
    *,
    task: NotesSynthesizerSectionTask,
    book_title: str,
    run_id: str,
    llm: NotesGroqStructuredLLM,
) -> NotesSynthesizerSectionTask:
    input_data = NotesSynthesizerInput(
        book_id=run_id,
        book_title=book_title,
        tasks=[task.model_copy(deep=True)],
    )
    graph = build_notes_synthesizer_graph(llm)
    state = initialize_state(input_data)
    final_state = NotesSynthesizerState.model_validate(graph.invoke(state))

    if final_state.completed_tasks:
        return final_state.completed_tasks[0]
    if final_state.failed_tasks:
        return final_state.failed_tasks[0]

    fallback_task = task.model_copy(deep=True)
    fallback_task.errors.append("Notes graph finished without completed or failed task.")
    return fallback_task


def _run_single_writer_task(
    *,
    note: SectionNoteArtifact,
    book_title: str,
    run_id: str,
    llm: WriterGroqStructuredLLM,
) -> WriterSectionTask:
    note_payload = _build_single_notes_bundle([note]).model_dump(mode="json")
    writer_tasks = build_tasks_from_notes_bundle(note_payload)
    if not writer_tasks:
        raise RuntimeError(f"No Writer task could be built for section '{note.section_id}'.")

    input_data = WriterInput(
        book_id=run_id,
        book_title=book_title,
        tasks=[writer_tasks[0]],
    )
    graph = build_writer_graph(llm)
    state = initialize_writer_state(input_data)
    final_state = WriterState.model_validate(graph.invoke(state))

    if final_state.completed_tasks:
        return final_state.completed_tasks[0]
    if final_state.failed_tasks:
        return final_state.failed_tasks[0]

    fallback_task = writer_tasks[0].model_copy(deep=True)
    fallback_task.errors.append("Writer graph finished without completed or failed task.")
    return fallback_task


def _run_single_reviewer_task(
    *,
    note: SectionNoteArtifact,
    draft: SectionDraft,
    llm_client: LLMClientProtocol,
) -> ReviewerSectionTask:
    notes_bundle = _build_single_notes_bundle([note])
    writer_bundle = _build_single_writer_bundle([draft])
    reviewer_tasks = build_reviewer_tasks(
        notes_bundle=notes_bundle,
        writer_bundle=writer_bundle,
    )
    if not reviewer_tasks:
        raise RuntimeError(f"No Reviewer task could be built for section '{note.section_id}'.")

    return review_section_safe(
        task=reviewer_tasks[0],
        llm_client=llm_client,
    )


def _build_notes_state(
    *,
    run_id: str,
    book_title: str,
    original_tasks: list[NotesSynthesizerSectionTask],
    results: list[SectionPipelineJobResult],
) -> NotesSynthesizerState:
    completed = [
        item.notes_task
        for item in results
        if item.notes_task is not None and item.notes_task.synthesized_note is not None
    ]
    failed = [
        item.notes_task
        for item in results
        if item.notes_task is not None and item.notes_task.synthesized_note is None
    ]
    failed_section_ids = {task.section_id for task in failed}

    completed_section_ids = {task.section_id for task in completed}
    for task in original_tasks:
        if task.section_id in completed_section_ids or task.section_id in failed_section_ids:
            continue
        fallback_task = task.model_copy(deep=True)
        fallback_task.errors.append("Section did not complete notes synthesis.")
        failed.append(fallback_task)

    notes = [task.synthesized_note for task in completed if task.synthesized_note is not None]

    return NotesSynthesizerState(
        book_id=run_id,
        book_title=book_title,
        pending_tasks=[],
        completed_tasks=completed,
        failed_tasks=failed,
        active_task=None,
        output_bundle=_build_single_notes_bundle(notes),
        run_warnings=[],
        run_errors=[
            item.error_message
            for item in results
            if item.error_message and item.notes_task is not None and item.notes_task.synthesized_note is None
        ],
    )


def _build_writer_state(
    *,
    run_id: str,
    book_title: str,
    results: list[SectionPipelineJobResult],
) -> WriterState:
    completed = [
        item.writer_task
        for item in results
        if item.writer_task is not None and item.writer_task.draft is not None
    ]
    failed = [
        item.writer_task
        for item in results
        if item.writer_task is not None and item.writer_task.draft is None
    ]
    drafts = [task.draft for task in completed if task.draft is not None]

    return WriterState(
        book_id=run_id,
        book_title=book_title,
        pending_tasks=[],
        completed_tasks=completed,
        failed_tasks=failed,
        active_task=None,
        output_bundle=_build_single_writer_bundle(drafts),
        run_warnings=[],
        run_errors=[
            item.error_message
            for item in results
            if item.error_message and item.writer_task is not None and item.writer_task.draft is None
        ],
    )


def _build_review_bundle(results: list[SectionPipelineJobResult]) -> ReviewBundle:
    sections = [
        ReviewerSectionResult(
            section_input=item.reviewer_task.section_input,
            section_output=item.reviewer_task.section_output,
        )
        for item in results
        if item.reviewer_task is not None and item.reviewer_task.section_output is not None
    ]

    approved = sum(1 for item in sections if item.section_output.review_status == ReviewStatus.APPROVED)
    revised = sum(1 for item in sections if item.section_output.review_status == ReviewStatus.REVISED)
    flagged = sum(1 for item in sections if item.section_output.review_status == ReviewStatus.FLAGGED)

    practicality_scores = []
    code_coverage_scores = []
    learning_depth_scores = []
    visual_richness_scores = []
    for section in sections:
        scores = section.section_output.quality_scores
        if scores is None:
            continue
        practicality_scores.append(scores.practicality_score)
        code_coverage_scores.append(scores.code_coverage_score)
        learning_depth_scores.append(scores.learning_depth_score)
        visual_richness_scores.append(scores.visual_richness_score)

    return ReviewBundle(
        metadata=ReviewBundleMetadata(
            total_sections=len(sections),
            approved_sections=approved,
            revised_sections=revised,
            flagged_sections=flagged,
            avg_practicality_score=_avg(practicality_scores),
            avg_code_coverage_score=_avg(code_coverage_scores),
            avg_learning_depth_score=_avg(learning_depth_scores),
            avg_visual_richness_score=_avg(visual_richness_scores),
        ),
        sections=sections,
    )


def _build_single_notes_bundle(notes: list[SectionNoteArtifact]) -> NotesSynthesisBundle:
    ready = sum(1 for note in notes if note.synthesis_status == SynthesisStatus.READY)
    partial = sum(1 for note in notes if note.synthesis_status == SynthesisStatus.PARTIAL)
    blocked = len(notes) - ready - partial
    return NotesSynthesisBundle(
        section_notes=notes,
        total_sections=len(notes),
        ready_sections=ready,
        partial_sections=partial,
        blocked_sections=blocked,
    )


def _build_single_writer_bundle(drafts: list[SectionDraft]) -> WriterOutputBundle:
    ready = sum(1 for draft in drafts if draft.writing_status == WritingStatus.READY)
    partial = sum(1 for draft in drafts if draft.writing_status == WritingStatus.PARTIAL)
    blocked = len(drafts) - ready - partial
    return WriterOutputBundle(
        section_drafts=drafts,
        total_sections=len(drafts),
        ready_sections=ready,
        partial_sections=partial,
        blocked_sections=blocked,
    )


def _build_pipeline_summary(
    *,
    max_workers: int,
    results: list[SectionPipelineJobResult],
) -> dict[str, Any]:
    failed_results = [item for item in results if item.failed]
    return {
        "mode": "parallel_section_pipeline",
        "max_workers": max_workers,
        "total_sections": len(results),
        "completed_sections": len(results) - len(failed_results),
        "failed_sections": len(failed_results),
        "failed_section_ids": [item.section_id for item in failed_results],
        "failure_messages": {
            item.section_id: item.error_message
            for item in failed_results
            if item.error_message
        },
        "section_timings": {
            item.section_id: item.timings
            for item in results
        },
    }


def _format_task_error(task: Any, layer_name: str) -> str:
    errors = getattr(task, "errors", None) or []
    if errors:
        return f"{layer_name} failed: {'; '.join(errors)}"
    return f"{layer_name} failed without a detailed error."


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _read_positive_int_env(*names: str, default: int) -> int:
    for name in names:
        value = os.getenv(name)
        if value is None or not value.strip():
            continue
        try:
            parsed = int(value)
        except ValueError:
            continue
        if parsed > 0:
            return parsed
    return default
