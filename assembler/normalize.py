from __future__ import annotations

import re
from collections import defaultdict

from planner_agent.schemas import BookPlan
from reviewer.schemas import ReviewBundle

from .ids import build_chapter_id, build_section_id, slugify
from .schemas import (
    AssemblerPlannerBook,
    AssemblerPlannerChapter,
    AssemblerPlannerSection,
    AssemblerReviewedSection,
    AssemblyFrontMatter,
)


def normalize_book_plan(book_plan: BookPlan) -> AssemblerPlannerBook:
    normalized_chapters: list[AssemblerPlannerChapter] = []

    sorted_chapters = sorted(book_plan.chapters, key=lambda chapter: chapter.chapter_number)

    for chapter in sorted_chapters:
        chapter_title = _clean_text(chapter.title)
        chapter_goal = _clean_text(chapter.chapter_goal)
        chapter_id = build_chapter_id(
            chapter_number=chapter.chapter_number,
            chapter_title=chapter_title,
        )

        normalized_sections: list[AssemblerPlannerSection] = []

        for section_number, section in enumerate(chapter.sections, start=1):
            section_title = _clean_text(section.title)
            section_goal = _clean_text(section.goal)

            normalized_sections.append(
                AssemblerPlannerSection(
                    section_id=build_section_id(
                        chapter_number=chapter.chapter_number,
                        section_title=section_title,
                    ),
                    chapter_id=chapter_id,
                    chapter_number=chapter.chapter_number,
                    section_number=section_number,
                    chapter_title=chapter_title,
                    section_title=section_title,
                    section_goal=section_goal,
                    estimated_words=section.estimated_words,
                    key_questions=_normalize_str_list(section.key_questions),
                )
            )

        normalized_chapters.append(
            AssemblerPlannerChapter(
                chapter_id=chapter_id,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter_title,
                chapter_goal=chapter_goal,
                sections=normalized_sections,
            )
        )

    return AssemblerPlannerBook(
        title=_clean_text(book_plan.title),
        audience=_clean_text(book_plan.audience),
        tone=_clean_text(book_plan.tone),
        depth=_clean_text(book_plan.depth),
        chapters=normalized_chapters,
    )


def build_front_matter(book: AssemblerPlannerBook) -> AssemblyFrontMatter:
    return AssemblyFrontMatter(
        title=book.title,
        audience=book.audience,
        tone=book.tone,
        depth=book.depth,
    )


def normalize_review_bundle(
    review_bundle: ReviewBundle,
    planner_book: AssemblerPlannerBook | None = None,
) -> list[AssemblerReviewedSection]:
    # Build a lookup of planner section IDs grouped by chapter number so we can
    # snap reviewer IDs back to the canonical planner ID when the LLM drifted
    # the section title slightly.
    planner_sections_by_chapter: dict[int, list[AssemblerPlannerSection]] = defaultdict(list)
    if planner_book is not None:
        for chapter in planner_book.chapters:
            for section in chapter.sections:
                planner_sections_by_chapter[chapter.chapter_number].append(section)

    normalized_sections: list[AssemblerReviewedSection] = []

    for result in review_bundle.sections:
        section_input = result.section_input
        section_output = result.section_output
        reviewer_title = _clean_text(section_output.section_title)
        raw_section_id = _clean_text(section_output.section_id)

        # Attempt to resolve the canonical planner section ID *and* title.
        # When the LLM drifts the section title, both the ID and the title must
        # be snapped to the planner's ground-truth values so that the downstream
        # title-mismatch validator passes.
        resolved_id, canonical_title = _resolve_section_id(
            raw_section_id=raw_section_id,
            reviewer_title=reviewer_title,
            planner_sections_by_chapter=planner_sections_by_chapter,
        )
        # Prefer the planner's canonical title; fall back to the reviewer's.
        section_title = canonical_title if canonical_title is not None else reviewer_title

        normalized_sections.append(
            AssemblerReviewedSection(
                section_id=resolved_id,
                section_title=section_title,
                reviewed_content=_normalize_prose(section_output.reviewed_content),
                review_status=section_output.review_status,
                citations_used=_normalize_str_list(section_output.citations_used),
                applied_changes_summary=_normalize_str_list(
                    section_output.applied_changes_summary
                ),
                reviewer_warnings=list(section_output.reviewer_warnings),
                synthesis_status=_clean_text(section_input.synthesis_status).lower(),
                writing_status=_clean_text(section_input.writing_status).lower(),
                central_thesis=_clean_text(section_input.central_thesis),
            )
        )

    return normalized_sections


def build_reviewed_section_map(
    sections: list[AssemblerReviewedSection],
) -> dict[str, AssemblerReviewedSection]:
    return {section.section_id: section for section in sections}


def _resolve_section_id(
    *,
    raw_section_id: str,
    reviewer_title: str,
    planner_sections_by_chapter: dict[int, list[AssemblerPlannerSection]],
) -> tuple[str, str | None]:
    """Return (canonical_section_id, canonical_title | None) for the reviewer section.

    When a planner section is matched via fuzzy title overlap the planner's
    canonical section_id *and* section_title are both returned so that the
    caller can adopt the ground-truth title and avoid title-mismatch errors.
    When no planner match is found, canonical_title is None and the caller
    should keep the reviewer's original title.

    Strategy:
    1. Extract the chapter number from the reviewer's raw section_id.
    2. Among planner sections for that chapter, find the one whose title has the
       highest Jaccard token-overlap with the reviewer's (potentially drifted)
       title.
    3. If the best match exceeds the minimum overlap threshold, return
       (planner.section_id, planner.section_title).
    4. Otherwise rebuild the ID from the reviewer's own title and return
       (rebuilt_id, None) so the validator can report a clean mismatch.
    """
    chapter_match = re.search(r"\bchapter-(\d+)\b", raw_section_id)
    if chapter_match and reviewer_title:
        chapter_number = int(chapter_match.group(1))
        planner_sections = planner_sections_by_chapter.get(chapter_number, [])
        if planner_sections:
            best_section = _best_title_match(reviewer_title, planner_sections)
            if best_section is not None:
                # Return both the canonical ID *and* the canonical title.
                return best_section.section_id, best_section.section_title
        # No planner context or no good match – rebuild from reviewer title.
        return build_section_id(
            chapter_number=chapter_number,
            section_title=reviewer_title,
        ), None
    return _normalize_section_id_text(raw_section_id), None


def _best_title_match(
    reviewer_title: str,
    planner_sections: list[AssemblerPlannerSection],
    min_overlap: float = 0.5,
) -> AssemblerPlannerSection | None:
    """Return the planner section whose title best token-overlaps the reviewer title.

    Overlap is computed as:
        |intersection(reviewer_tokens, planner_tokens)| / |union(reviewer_tokens, planner_tokens)|
    (Jaccard similarity on lowercased word tokens.)
    """
    reviewer_tokens = set(reviewer_title.lower().split())
    if not reviewer_tokens:
        return None

    best_section: AssemblerPlannerSection | None = None
    best_score: float = -1.0

    for section in planner_sections:
        planner_tokens = set(section.section_title.lower().split())
        if not planner_tokens:
            continue
        intersection = len(reviewer_tokens & planner_tokens)
        union = len(reviewer_tokens | planner_tokens)
        score = intersection / union if union else 0.0
        if score > best_score:
            best_score = score
            best_section = section

    if best_score >= min_overlap:
        return best_section
    return None


def _canonical_review_section_id(*, section_id: str, section_title: str) -> str:
    """Legacy helper kept for backwards-compat (called from tests). Prefer _resolve_section_id."""
    chapter_match = re.search(r"\bchapter-(\d+)\b", section_id)
    if chapter_match and section_title:
        return build_section_id(
            chapter_number=int(chapter_match.group(1)),
            section_title=section_title,
        )
    return _normalize_section_id_text(section_id)


def _normalize_section_id_text(section_id: str) -> str:
    cleaned = section_id.strip().lower().replace("_", "-")
    if not cleaned:
        return ""
    chapter_section_match = re.match(r"^(chapter-\d+)-section-(.+)$", cleaned)
    if chapter_section_match:
        return f"{chapter_section_match.group(1)}-section-{slugify(chapter_section_match.group(2))}"
    chapter_match = re.match(r"^(chapter-\d+)-(.+)$", cleaned)
    if chapter_match:
        return f"{chapter_match.group(1)}-section-{slugify(chapter_match.group(2))}"
    return slugify(cleaned)


def _normalize_prose(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized = "\n".join(lines).strip()
    return normalized


def _normalize_str_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = _clean_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)

    return cleaned


def _clean_text(value: str) -> str:
    return " ".join(str(value).split()).strip()
