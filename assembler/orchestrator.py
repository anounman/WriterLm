from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from planner_agent.schemas import BookPlan
from reviewer.schemas import ReviewBundle, ReviewStatus

from .ids import build_latex_label
from .latex import render_latex_manuscript
from .normalize import (
    build_front_matter,
    build_reviewed_section_map,
    normalize_book_plan,
    normalize_review_bundle,
)
from .schemas import (
    AssembledChapter,
    AssembledSection,
    AssemblyArtifacts,
    AssemblyBundle,
    AssemblyBundleMetadata,
    AssemblySectionRegistryEntry,
    AssemblySourceArtifacts,
    AssemblyStatus,
)
from .validator import (
    validate_assembled_chapters,
    validate_planner_book,
    validate_planner_reviewer_alignment,
    validate_rendered_latex,
    validate_reviewed_sections,
)


def run_assembler(
    *,
    book_plan: BookPlan,
    review_bundle: ReviewBundle,
    book_plan_path: str | Path,
    review_bundle_path: str | Path,
    latex_output_path: str | Path,
) -> AssemblyArtifacts:
    normalized_book = normalize_book_plan(book_plan)
    normalized_reviewed_sections = normalize_review_bundle(review_bundle, planner_book=normalized_book)

    validate_planner_book(normalized_book)
    validate_reviewed_sections(normalized_reviewed_sections)
    validate_planner_reviewer_alignment(normalized_book, normalized_reviewed_sections)

    reviewed_by_id = build_reviewed_section_map(normalized_reviewed_sections)
    assembled_chapters = _assemble_chapters(normalized_book.chapters, reviewed_by_id)

    validate_assembled_chapters(assembled_chapters)

    front_matter = build_front_matter(normalized_book)
    latex_manuscript = render_latex_manuscript(
        front_matter=front_matter,
        chapters=assembled_chapters,
    )

    validate_rendered_latex(
        latex_content=latex_manuscript.content,
        assembled_chapters=assembled_chapters,
    )

    flagged_section_ids = [
        section.section_id
        for chapter in assembled_chapters
        for section in chapter.sections
        if section.review_status == ReviewStatus.FLAGGED
    ]

    section_registry = [
        AssemblySectionRegistryEntry(
            section_id=section.section_id,
            chapter_id=section.chapter_id,
            chapter_number=section.chapter_number,
            section_number=section.section_number,
            chapter_title=section.chapter_title,
            section_title=section.section_title,
            review_status=section.review_status,
            flagged=section.review_status == ReviewStatus.FLAGGED,
            latex_label=section.latex_label,
            content_hash=section.content_hash,
        )
        for chapter in assembled_chapters
        for section in chapter.sections
    ]

    approved_sections = sum(
        1
        for chapter in assembled_chapters
        for section in chapter.sections
        if section.review_status == ReviewStatus.APPROVED
    )
    revised_sections = sum(
        1
        for chapter in assembled_chapters
        for section in chapter.sections
        if section.review_status == ReviewStatus.REVISED
    )
    flagged_sections = len(flagged_section_ids)

    assembly_notes: list[str] = []
    if flagged_section_ids:
        assembly_notes.append(
            "Assembler included flagged sections in the manuscript and preserved their metadata."
        )

    assembly_bundle = AssemblyBundle(
        metadata=AssemblyBundleMetadata(
            assembly_status=(
                AssemblyStatus.READY_WITH_FLAGS
                if flagged_section_ids
                else AssemblyStatus.READY
            ),
            book_title=normalized_book.title,
            chapter_count=len(assembled_chapters),
            planned_section_count=sum(len(chapter.sections) for chapter in normalized_book.chapters),
            assembled_section_count=len(section_registry),
            approved_sections=approved_sections,
            revised_sections=revised_sections,
            flagged_sections=flagged_sections,
            generated_at=datetime.now(timezone.utc),
            latex_output_path=str(latex_output_path),
        ),
        source_artifacts=AssemblySourceArtifacts(
            book_plan_path=str(book_plan_path),
            review_bundle_path=str(review_bundle_path),
        ),
        front_matter=front_matter,
        chapters=assembled_chapters,
        section_registry=section_registry,
        flagged_section_ids=flagged_section_ids,
        full_book_text=_build_full_book_text(normalized_book.title, assembled_chapters),
        assembly_notes=assembly_notes,
    )

    return AssemblyArtifacts(
        assembly_bundle=assembly_bundle,
        latex_manuscript=latex_manuscript,
    )


def _assemble_chapters(chapters, reviewed_by_id) -> list[AssembledChapter]:
    assembled_chapters: list[AssembledChapter] = []

    for chapter in chapters:
        assembled_sections: list[AssembledSection] = []

        for section in chapter.sections:
            reviewed = reviewed_by_id[section.section_id]
            assembled_sections.append(
                AssembledSection(
                    section_id=section.section_id,
                    chapter_id=chapter.chapter_id,
                    chapter_number=chapter.chapter_number,
                    section_number=section.section_number,
                    chapter_title=chapter.chapter_title,
                    section_title=section.section_title,
                    planner_goal=section.section_goal,
                    estimated_words=section.estimated_words,
                    review_status=reviewed.review_status,
                    synthesis_status=reviewed.synthesis_status,
                    writing_status=reviewed.writing_status,
                    reviewer_warnings=list(reviewed.reviewer_warnings),
                    citations_used=list(reviewed.citations_used),
                    applied_changes_summary=list(reviewed.applied_changes_summary),
                    content=reviewed.reviewed_content,
                    content_hash=_sha256(reviewed.reviewed_content),
                    latex_label=build_latex_label(
                        chapter_number=chapter.chapter_number,
                        section_number=section.section_number,
                        section_id=section.section_id,
                    ),
                )
            )

        assembled_chapters.append(
            AssembledChapter(
                chapter_id=chapter.chapter_id,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.chapter_title,
                chapter_goal=chapter.chapter_goal,
                sections=assembled_sections,
            )
        )

    return assembled_chapters


def _build_full_book_text(title: str, chapters: list[AssembledChapter]) -> str:
    parts = [title]

    for chapter in chapters:
        parts.append("")
        parts.append(f"# {chapter.chapter_title}")

        for section in chapter.sections:
            parts.append("")
            parts.append(f"## {section.section_title}")
            parts.append("")
            parts.append(section.content)

    return "\n".join(parts).strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
