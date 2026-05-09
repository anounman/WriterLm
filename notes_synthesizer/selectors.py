from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .schemas import CoverageSignal, SectionSynthesisInput, SourceReference


MAX_KEY_CONCEPTS = 12
MAX_EVIDENCE_ITEMS = 20
MAX_WRITING_GUIDANCE_ITEMS = 10
MAX_OPEN_QUESTIONS = 10
MAX_PLANNER_CONTEXT_CHARS = 500
MAX_EVIDENCE_ITEM_CHARS = 300
MAX_SOURCE_REFERENCES = 8


def _as_clean_string(value: Any) -> Optional[str]:
    """
    Convert arbitrary input to a stripped string.
    Return None for empty/invalid values.
    """
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    cleaned = str(value).strip()
    return cleaned or None


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    """
    Remove duplicates while preserving original order.
    Empty items are removed.
    """
    seen = set()
    output: List[str] = []

    for item in items:
        cleaned = _as_clean_string(item)
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)

    return output


def _clip_text(text: str, max_chars: int) -> str:
    """
    Light character clipping to keep synthesis input compact.
    """
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _extract_list_of_strings(value: Any) -> List[str]:
    """
    Normalize a value into a flat list of strings.

    Supports:
    - list[str]
    - list[dict] where useful text fields exist
    - single string
    - None
    """
    if value is None:
        return []

    if isinstance(value, str):
        cleaned = _as_clean_string(value)
        return [cleaned] if cleaned else []

    if not isinstance(value, list):
        cleaned = _as_clean_string(value)
        return [cleaned] if cleaned else []

    output: List[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = _as_clean_string(item)
            if cleaned:
                output.append(cleaned)
            continue

        if isinstance(item, dict):
            for key in (
                "text",
                "summary",
                "statement",
                "fact",
                "claim",
                "note",
                "description",
                "guidance",
                "question",
                "title",
            ):
                if key in item:
                    cleaned = _as_clean_string(item.get(key))
                    if cleaned:
                        output.append(cleaned)
                        break
            continue

        cleaned = _as_clean_string(item)
        if cleaned:
            output.append(cleaned)

    return _dedupe_preserve_order(output)


def _extract_source_ids(source_references: Any, evidence_items: Any) -> List[str]:
    """
    Collect source IDs from researcher artifacts.

    Supports common shapes such as:
    - source_references: [{"source_id": "src_1"}, ...]
    - source_references: [{"id": "src_1"}, ...]
    - source_references: ["src_1", "src_2"]
    - evidence_items: [{"source_id": "..."}], [{"source_ids": [...]}], etc.
    """
    collected: List[str] = []

    def add_source_id(value: Any) -> None:
        cleaned = _as_clean_string(value)
        if cleaned:
            collected.append(cleaned)

    if isinstance(source_references, list):
        for item in source_references:
            if isinstance(item, str):
                add_source_id(item)
            elif isinstance(item, dict):
                add_source_id(item.get("source_id"))
                add_source_id(item.get("id"))

    if isinstance(evidence_items, list):
        for item in evidence_items:
            if not isinstance(item, dict):
                continue
            add_source_id(item.get("source_id"))
            if isinstance(item.get("source_ids"), list):
                for source_id in item["source_ids"]:
                    add_source_id(source_id)

    return _dedupe_preserve_order(collected)


def _extract_source_references(source_references: Any) -> List[SourceReference]:
    output: List[SourceReference] = []
    seen: set[str] = set()

    if not isinstance(source_references, list):
        return output

    for item in source_references:
        if isinstance(item, str):
            source_id = _as_clean_string(item)
            if source_id and source_id not in seen:
                seen.add(source_id)
                output.append(SourceReference(source_id=source_id))
            continue

        if not isinstance(item, dict):
            continue

        source_id = _as_clean_string(item.get("source_id") or item.get("id"))
        if not source_id or source_id in seen:
            continue

        seen.add(source_id)
        output.append(
            SourceReference(
                source_id=source_id,
                title=_as_clean_string(item.get("title")) or source_id,
                url=_as_clean_string(item.get("url") or item.get("canonical_url")) or "",
            )
        )

    return output[:MAX_SOURCE_REFERENCES]


def _normalize_coverage_signal(coverage_report: Any) -> CoverageSignal:
    """
    Normalize uneven research coverage formats into a stable enum.

    Heuristics:
    - sufficient / strong / complete -> SUFFICIENT
    - partial / mixed / limited -> PARTIAL
    - weak / poor / insufficient / missing -> WEAK
    - fallback default -> PARTIAL
    """
    candidate_values: List[str] = []

    if isinstance(coverage_report, str):
        cleaned = _as_clean_string(coverage_report)
        if cleaned:
            candidate_values.append(cleaned.lower())

    elif isinstance(coverage_report, dict):
        for key in ("status", "coverage_status", "strength", "assessment", "summary"):
            value = coverage_report.get(key)
            cleaned = _as_clean_string(value)
            if cleaned:
                candidate_values.append(cleaned.lower())

    joined = " ".join(candidate_values)

    if any(token in joined for token in ("sufficient", "strong", "complete", "good", "adequate")):
        return CoverageSignal.SUFFICIENT

    if any(token in joined for token in ("weak", "poor", "insufficient", "missing", "thin")):
        return CoverageSignal.WEAK

    if any(token in joined for token in ("partial", "mixed", "limited", "uneven", "incomplete")):
        return CoverageSignal.PARTIAL

    return CoverageSignal.PARTIAL


def _extract_planner_context(planner_section: Dict[str, Any]) -> Optional[str]:
    """
    Build a short planner-derived context string.

    Keep this small. It is only supporting context, not a second prompt.
    """
    parts: List[str] = []

    for key in ("chapter_title", "chapter_goal", "section_position", "summary", "notes"):
        value = planner_section.get(key)
        cleaned = _as_clean_string(value)
        if cleaned:
            parts.append(f"{key}: {cleaned}")

    if not parts:
        return None

    return _clip_text(" | ".join(parts), MAX_PLANNER_CONTEXT_CHARS)


def _extract_evidence_statements(evidence_items: Any) -> List[str]:
    """
    Convert researcher evidence items into compact textual evidence statements.

    This intentionally avoids carrying full raw evidence structures forward.
    """
    if not isinstance(evidence_items, list):
        return []

    output: List[str] = []

    for item in evidence_items:
        if isinstance(item, str):
            cleaned = _as_clean_string(item)
            if cleaned:
                output.append(_clip_text(cleaned, MAX_EVIDENCE_ITEM_CHARS))
            continue

        if not isinstance(item, dict):
            cleaned = _as_clean_string(item)
            if cleaned:
                output.append(_clip_text(cleaned, MAX_EVIDENCE_ITEM_CHARS))
            continue

        parts: List[str] = []

        for key in ("content", "claim", "statement", "fact", "summary", "description", "note"):
            value = item.get(key)
            cleaned = _as_clean_string(value)
            if cleaned:
                parts.append(cleaned)
                break

        for key in ("relevance_note", "relevance", "reason", "importance"):
            value = item.get(key)
            cleaned = _as_clean_string(value)
            if cleaned:
                parts.append(f"{key}: {cleaned}")
                break

        combined = " | ".join(parts)
        cleaned_combined = _as_clean_string(combined)
        if cleaned_combined:
            output.append(_clip_text(cleaned_combined, MAX_EVIDENCE_ITEM_CHARS))

    return _dedupe_preserve_order(output)[:MAX_EVIDENCE_ITEMS]


def _extract_knowledge_map_statements(knowledge_map: Any) -> tuple[list[str], list[str], list[str], list[str]]:
    if not isinstance(knowledge_map, dict):
        return [], [], [], []

    evidence: list[str] = []
    concepts: list[str] = []
    guidance: list[str] = []
    questions: list[str] = []

    def read_items(key: str, prefix: str) -> None:
        raw_items = knowledge_map.get(key)
        if not isinstance(raw_items, list):
            return
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            content = _as_clean_string(item.get("content"))
            label = _as_clean_string(item.get("label"))
            source_ids = _extract_list_of_strings(item.get("supporting_source_ids"))
            uncertainty = _as_clean_string(item.get("uncertainty_flag"))
            if content:
                support = f" | sources: {', '.join(source_ids)}" if source_ids else ""
                caveat = f" | uncertainty: {uncertainty}" if uncertainty else ""
                evidence.append(_clip_text(f"{prefix}: {label or key}: {content}{support}{caveat}", MAX_EVIDENCE_ITEM_CHARS))
            if label:
                concepts.append(label)

    read_items("key_claims", "claim")
    read_items("definitions", "definition")
    read_items("examples", "example")
    read_items("conflicting_viewpoints", "conflict")

    guidance.extend(_extract_list_of_strings(knowledge_map.get("recommended_framing")))
    guidance.extend(f"Uncertainty: {item}" for item in _extract_list_of_strings(knowledge_map.get("uncertainty_flags")))
    questions.extend(_extract_list_of_strings(knowledge_map.get("open_questions")))
    return evidence, concepts, guidance, questions


def build_section_synthesis_input(
    planner_section: Dict[str, Any],
    research_section: Dict[str, Any],
) -> SectionSynthesisInput:
    """
    Build the compact SectionSynthesisInput from upstream planner/research artifacts.

    This function is intentionally deterministic and cheap:
    - no network
    - no LLM
    - no source fetching
    - no raw document rereading
    """
    section_id = _as_clean_string(
        research_section.get("section_id") or planner_section.get("section_id")
    )
    if not section_id:
        raise ValueError("Missing section_id in planner/research section inputs.")

    section_title = _as_clean_string(
        research_section.get("section_title") or planner_section.get("section_title")
    )
    if not section_title:
        raise ValueError(f"Missing section_title for section_id={section_id!r}.")

    section_objective = _as_clean_string(
        research_section.get("section_objective") or planner_section.get("section_objective")
    )
    if not section_objective:
        raise ValueError(f"Missing section_objective for section_id={section_id!r}.")

    km_evidence, km_concepts, km_guidance, km_questions = _extract_knowledge_map_statements(
        research_section.get("knowledge_map")
    )

    key_concepts = _dedupe_preserve_order(_extract_list_of_strings(
        research_section.get("key_concepts") or planner_section.get("key_concepts")
    ) + km_concepts)[:MAX_KEY_CONCEPTS]

    writing_guidance = _dedupe_preserve_order(
        _extract_list_of_strings(research_section.get("writing_guidance")) + km_guidance
    )[:MAX_WRITING_GUIDANCE_ITEMS]

    open_questions = _dedupe_preserve_order(
        _extract_list_of_strings(research_section.get("open_questions")) + km_questions
    )[:MAX_OPEN_QUESTIONS]

    evidence_items = _dedupe_preserve_order(
        _extract_evidence_statements(research_section.get("evidence_items")) + km_evidence
    )[:MAX_EVIDENCE_ITEMS]

    coverage_signal = _normalize_coverage_signal(research_section.get("coverage_report"))

    available_source_ids = _extract_source_ids(
        source_references=research_section.get("source_references"),
        evidence_items=research_section.get("evidence_items"),
    )
    source_references = _extract_source_references(research_section.get("source_references"))

    planner_context = _extract_planner_context(planner_section)

    # Extract content requirements from planner section
    content_reqs = planner_section.get("content_requirements") or {}
    must_include_code = False
    must_include_diagram = False
    suggested_diagram_type = None
    book_state_summary = ""
    continuity_rules: list[str] = []
    chapter_dependencies: list[str] = []
    implementation_strategy = None
    progression_strategy = None
    book_contract: dict[str, Any] = {}

    if isinstance(content_reqs, dict):
        must_include_code = bool(content_reqs.get("must_include_code", False))
        must_include_diagram = bool(content_reqs.get("must_include_diagram", False))
        suggested_diagram_type = _as_clean_string(content_reqs.get("suggested_diagram_type"))

    book_state = planner_section.get("book_state")
    if isinstance(book_state, dict):
        book_state_summary = _as_clean_string(book_state.get("book_state_summary")) or ""
        continuity_rules = _extract_list_of_strings(book_state.get("continuity_rules"))
        chapter_dependencies = _extract_list_of_strings(book_state.get("chapter_dependencies"))
        implementation_strategy = _as_clean_string(book_state.get("implementation_strategy"))
        progression_strategy = _as_clean_string(book_state.get("progression_strategy"))
        raw_contract = book_state.get("book_contract")
        if isinstance(raw_contract, dict):
            book_contract = raw_contract

    return SectionSynthesisInput(
        section_id=section_id,
        section_title=section_title,
        section_objective=section_objective,
        planner_context=planner_context,
        key_concepts=key_concepts,
        evidence_items=evidence_items,
        writing_guidance=writing_guidance,
        open_questions=open_questions,
        coverage_signal=coverage_signal,
        available_source_ids=available_source_ids,
        source_references=source_references,
        must_include_code=must_include_code,
        must_include_diagram=must_include_diagram,
        suggested_diagram_type=suggested_diagram_type,
        book_state_summary=book_state_summary,
        continuity_rules=continuity_rules,
        chapter_dependencies=chapter_dependencies,
        implementation_strategy=implementation_strategy,
        progression_strategy=progression_strategy,
        book_contract=book_contract,
    )
