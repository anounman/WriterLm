from __future__ import annotations

import json
from pathlib import Path

from .schemas import ReviewBundle
from .schemas import ReviewerSectionInput
from .state import ReviewerSectionTask

from notes_synthesizer.schemas import NotesSynthesisBundle
from writer.schemas import WriterOutputBundle


def load_notes_bundle(path: str | Path) -> NotesSynthesisBundle:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return NotesSynthesisBundle.model_validate(data)


def load_writer_bundle(path: str | Path) -> WriterOutputBundle:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return WriterOutputBundle.model_validate(data)


def build_reviewer_tasks(
    notes_bundle: NotesSynthesisBundle,
    writer_bundle: WriterOutputBundle,
) -> list[ReviewerSectionTask]:
    notes_by_section_id = {
        section.section_id: section
        for section in notes_bundle.section_notes
    }
    writer_by_section_id = {
        section.section_id: section
        for section in writer_bundle.section_drafts
    }

    missing_in_writer = sorted(set(notes_by_section_id) - set(writer_by_section_id))
    if missing_in_writer:
        raise ValueError(
            "Writer bundle is missing sections required by notes bundle: "
            f"{missing_in_writer}"
        )

    tasks: list[ReviewerSectionTask] = []

    for section_id, note_section in notes_by_section_id.items():
        writer_section = writer_by_section_id[section_id]

        if note_section.section_title.strip() != writer_section.section_title.strip():
            raise ValueError(
                f"Section title mismatch for section_id={section_id}: "
                f"notes='{note_section.section_title}' vs "
                f"writer='{writer_section.section_title}'"
            )

        section_input = ReviewerSectionInput(
            section_id=note_section.section_id,
            section_title=note_section.section_title,
            synthesis_status=note_section.synthesis_status,
            central_thesis=note_section.central_thesis,
            core_points=list(note_section.core_points),
            supporting_facts=[
                item.fact for item in note_section.supporting_facts
            ],
            examples=[
                item.example for item in note_section.examples
            ],
            important_caveats=list(note_section.important_caveats),
            unresolved_gaps=list(note_section.unresolved_gaps),
            recommended_flow=[
                step.instruction for step in note_section.recommended_flow
            ],
            writer_guidance=list(note_section.writer_guidance),
            allowed_citation_source_ids=list(note_section.allowed_citation_source_ids),
            must_include_code=getattr(note_section, "must_include_code", False),
            must_include_diagram=getattr(note_section, "must_include_diagram", False),
            book_contract=getattr(note_section, "book_contract", {}) or {},
            progression_strategy=getattr(note_section, "progression_strategy", None),
            writer_content=writer_section.content,
            writer_citations_used=list(writer_section.citations_used),
            writer_code_blocks_count=getattr(writer_section, "code_blocks_count", 0),
            writer_diagram_hints_count=len(getattr(writer_section, "diagram_hints", []) or []),
            writing_status=writer_section.writing_status,
        )

        tasks.append(ReviewerSectionTask(section_input=section_input))

    return tasks


def save_review_bundle(bundle: ReviewBundle, path: str | Path) -> None:
    Path(path).write_text(
        bundle.model_dump_json(indent=2),
        encoding="utf-8",
    )
