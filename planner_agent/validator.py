from __future__ import annotations

import re

from planner_agent.schemas import BookPlan, UserBookRequest


FOCUSED_BEGINNER_BANNED_CHAPTER_PATTERNS: list[tuple[str, str]] = [
    (r"\bfuture\s+(?:directions?|trends?|of|work|research|outlook)\b|\bfrontier\b|\bemerging\s+trends?\b", "future/frontier coverage"),
    (r"\bethic", "ethics coverage"),
    (r"\blegal\b|\bsocietal\b", "legal or societal coverage"),
    (r"\bcompliance\b|\bgovernance\b", "compliance or governance"),
    (
        r"\bproduction\b|\bscaling\b|\bscale\b|\bhigh[- ]availability\b|\benterprise\b",
        "advanced production or scaling",
    ),
    (
        r"\bci/cd\b|\bcontainer(?:ization)?\b|\bkubernetes\b|\borchestration\b|\bmonitoring\b|\balerting\b",
        "deployment operations",
    ),
    (r"\bcase studies\b|\breal[- ]world case", "broad case-study coverage"),
    (r"\bmultimodal\b|\bagentic\b", "advanced adjacent extension coverage"),
]

PRACTICAL_PAYOFF_PATTERNS = (
    "architecture",
    "component",
    "build",
    "implementation",
    "implement",
    "pipeline",
    "walkthrough",
    "tutorial",
    "debug",
    "prototype",
    "python",
    "train",
    "training",
    "fine-tune",
    "fine tuning",
    "fine-tuning",
    "hands-on",
    "worked example",
    "practice",
    "exercise",
    "problem",
    "solve",
)

BACKGROUND_PATTERNS = (
    "foundation",
    "fundamentals",
    "generative ai",
    "large language model",
    "llm",
    "transformer",
    "tokenization",
    "training",
)

RAG_SPECIFIC_PATTERNS = (
    "rag",
    "retrieval",
    "vector",
    "embedding",
    "search",
    "document",
    "context",
    "index",
    "pipeline",
)


def _normalized_text(*parts: str) -> str:
    return " ".join(part.strip().lower() for part in parts if part and part.strip())


def _total_sections(plan: BookPlan) -> int:
    return sum(len(chapter.sections) for chapter in plan.chapters)


def _find_first_practical_payoff_chapter(plan: BookPlan) -> int | None:
    for chapter in plan.chapters:
        chapter_text = _normalized_text(chapter.title, chapter.chapter_goal)
        if any(pattern in chapter_text for pattern in PRACTICAL_PAYOFF_PATTERNS):
            return chapter.chapter_number
    return None


def _count_background_only_chapters(plan: BookPlan) -> int:
    count = 0
    for chapter in plan.chapters:
        chapter_text = _normalized_text(chapter.title, chapter.chapter_goal)
        has_background = any(pattern in chapter_text for pattern in BACKGROUND_PATTERNS)
        has_rag_specific = any(pattern in chapter_text for pattern in RAG_SPECIFIC_PATTERNS)
        if has_background and not has_rag_specific:
            count += 1
    return count


def _count_rag_specific_chapters(plan: BookPlan) -> int:
    count = 0
    for chapter in plan.chapters:
        chapter_text = _normalized_text(chapter.title, chapter.chapter_goal)
        if any(pattern in chapter_text for pattern in RAG_SPECIFIC_PATTERNS):
            count += 1
    return count


def _request_is_rag_related(request: UserBookRequest) -> bool:
    return any(pattern in request.combined_intent_text for pattern in RAG_SPECIFIC_PATTERNS)


def validate_book_plan(plan: BookPlan, request: UserBookRequest) -> list[str]:
    issues: list[str] = []

    if not plan.title.strip():
        issues.append("Book title is empty.")

    if not plan.chapters:
        issues.append("No chapters defined.")
        return issues

    chapter_count = plan.get_chapter_count()
    if chapter_count < 3:
        issues.append("Book must have at least 3 chapters.")

    if request.chapter_count is not None and chapter_count != request.chapter_count:
        issues.append(
            f"Expected {request.chapter_count} chapters, but got {chapter_count}."
        )

    if request.project_based and not plan.running_project:
        issues.append(
            "Project-based book must have a running_project description."
        )

    seen_chapter_titles = set()

    for expected_number, chapter in enumerate(plan.chapters, start=1):
        normalized_chapter_title = chapter.title.strip().lower()

        if chapter.chapter_number != expected_number:
            issues.append(
                f"Chapter numbering is not sequential at '{chapter.title}': "
                f"expected {expected_number}, got {chapter.chapter_number}."
            )

        if not chapter.title.strip():
            issues.append(f"Chapter {chapter.chapter_number} has an empty title.")

        if normalized_chapter_title in seen_chapter_titles:
            issues.append(f"Duplicate chapter title: '{chapter.title}'.")
        seen_chapter_titles.add(normalized_chapter_title)

        if not chapter.chapter_goal.strip():
            issues.append(f"Chapter '{chapter.title}' has an empty goal.")

        if request.project_based and not chapter.project_milestone:
            issues.append(
                f"Chapter '{chapter.title}' is missing a project_milestone (required for project-based books)."
            )

        if not chapter.sections:
            issues.append(f"Chapter {chapter.chapter_number} has no sections.")

        if request.is_focused_beginner_guide:
            min_sections, max_sections = request.preferred_sections_per_chapter_range
            if not (min_sections <= len(chapter.sections) <= max_sections):
                issues.append(
                    f"Chapter '{chapter.title}' should have {min_sections} to {max_sections} "
                    f"sections for a focused beginner guide, but has {len(chapter.sections)}."
                )

        seen_section_titles = set()
        sections_with_no_content = 0

        for section in chapter.sections:
            normalized_section_title = section.title.strip().lower()

            if not section.title.strip():
                issues.append(
                    f"Section in Chapter {chapter.chapter_number} has an empty title."
                )

            if normalized_section_title in seen_section_titles:
                issues.append(
                    f"Duplicate section title '{section.title}' in Chapter {chapter.chapter_number}."
                )
            seen_section_titles.add(normalized_section_title)

            if not section.goal.strip():
                issues.append(
                    f"Section '{section.title}' in Chapter {chapter.chapter_number} has an empty goal."
                )

            if len(section.key_questions) == 0:
                issues.append(
                    f"Section '{section.title}' in Chapter {chapter.chapter_number} has no key questions."
                )

            if section.estimated_words <= 0:
                issues.append(
                    f"Section '{section.title}' in Chapter {chapter.chapter_number} has non-positive estimated words."
                )

            if (
                request.max_section_words is not None
                and section.estimated_words > request.max_section_words
            ):
                issues.append(
                    f"Section '{section.title}' in Chapter {chapter.chapter_number} exceeds "
                    f"max_section_words={request.max_section_words}."
                )

            cr = section.content_requirements
            if not cr.must_include_code and not cr.must_include_example and not cr.must_include_diagram:
                sections_with_no_content += 1
                issues.append(
                    f"Section '{section.title}' in Chapter {chapter.chapter_number} has no content "
                    f"requirements (code, example, or diagram). At least one must be true."
                )

        if sections_with_no_content > 0 and len(chapter.sections) > 0:
            ratio = sections_with_no_content / len(chapter.sections)
            if ratio > 0.5:
                issues.append(
                    f"Chapter '{chapter.title}' has too many sections ({sections_with_no_content}/{len(chapter.sections)}) "
                    f"with no content requirements."
                )

    if request.is_focused_beginner_guide:
        preferred_min, preferred_max = request.preferred_chapter_range
        if request.chapter_count is None and not (preferred_min <= chapter_count <= preferred_max):
            issues.append(
                f"Focused beginner practical guides should usually have {preferred_min} to "
                f"{preferred_max} chapters, but this plan has {chapter_count}."
            )

        max_total_sections = request.preferred_max_total_sections
        total_sections = _total_sections(plan)
        if max_total_sections is not None and total_sections > max_total_sections:
            issues.append(
                f"Focused beginner practical guides should have at most {max_total_sections} "
                f"total sections, but this plan has {total_sections}."
            )

        for chapter in plan.chapters:
            # Check only the title for banned patterns — goals often mention
            # excluded terms in passing (e.g. "prepare for small-scale production").
            chapter_title_text = _normalized_text(chapter.title)
            for pattern, label in FOCUSED_BEGINNER_BANNED_CHAPTER_PATTERNS:
                if re.search(pattern, chapter_title_text, flags=re.IGNORECASE):
                    issues.append(
                        f"Chapter '{chapter.title}' introduces excluded scope for a focused "
                        f"beginner guide: {label}."
                    )
                    break

        practical_payoff_chapter = _find_first_practical_payoff_chapter(plan)
        latest_practical = request.preferred_practical_payoff_latest_chapter
        if practical_payoff_chapter is None:
            issues.append(
                "Focused beginner practical guides must include a practical implementation "
                "or hands-on chapter, but none was detected."
            )
        elif latest_practical is not None and practical_payoff_chapter > latest_practical:
            issues.append(
                f"Practical payoff appears too late for a focused beginner guide: first "
                f"implementation-oriented chapter is Chapter {practical_payoff_chapter}, "
                f"but it should appear by Chapter {latest_practical}."
            )

        if _request_is_rag_related(request):
            background_only_count = _count_background_only_chapters(plan)
            rag_specific_count = _count_rag_specific_chapters(plan)
            if background_only_count > 1:
                issues.append(
                    f"Focused beginner RAG guides should not spend multiple chapters on broad "
                    f"background material alone, but this plan has {background_only_count} "
                    "background-only chapters."
                )
            if background_only_count >= max(2, rag_specific_count):
                issues.append(
                    "Background coverage outweighs RAG-specific content for a focused beginner guide."
                )

    return issues
