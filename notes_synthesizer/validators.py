from __future__ import annotations

from typing import List, Set

from .schemas import (
    CodeSnippet,
    DiagramSuggestion,
    SectionNoteArtifact,
    SectionSynthesisInput,
    SynthesisStatus,
    CoverageSignal,
)


MAX_CORE_POINTS = 8
MAX_FACTS = 15
MAX_EXAMPLES = 8
MAX_CAVEATS = 10
MAX_GAPS = 10
MAX_FLOW_STEPS = 10
MAX_WRITER_GUIDANCE = 10
MAX_REFERENCE_LINKS = 5


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    output: List[str] = []
    for item in items:
        if not item:
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output


def _filter_allowed_source_ids(
    source_ids: List[str],
    allowed: Set[str],
) -> List[str]:
    return [sid for sid in source_ids if sid in allowed]


def _title_to_class_name(title: str) -> str:
    parts = [part for part in re_split_non_alnum(title) if part]
    candidate = "".join(part.capitalize() for part in parts[:4])
    if not candidate:
        candidate = "Example"
    if candidate[0].isdigit():
        candidate = f"Example{candidate}"
    return candidate


def re_split_non_alnum(value: str) -> list[str]:
    current: list[str] = []
    parts: list[str] = []
    for char in value:
        if char.isalnum():
            current.append(char)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    return parts


def _fallback_code_snippet(note: SectionNoteArtifact) -> CodeSnippet:
    class_name = _title_to_class_name(note.section_title)
    topic = note.section_title.replace('"', "'")
    return CodeSnippet(
        language="python",
        description=f"Minimal executable scaffold for experimenting with {note.section_title}.",
        code=(
            f"class {class_name}Demo:\n"
            "    def __init__(self):\n"
            "        self.steps = []\n\n"
            "    def add_step(self, name, detail):\n"
            "        self.steps.append({'name': name, 'detail': detail})\n\n"
            "    def run(self):\n"
            "        for index, step in enumerate(self.steps, start=1):\n"
            "            print(f\"{index}. {step['name']}: {step['detail']}\")\n\n"
            "demo = "
            f"{class_name}Demo()\n"
            f"demo.add_step('Explore', 'Identify the moving parts in {topic}.')\n"
            "demo.add_step('Implement', 'Build the smallest working version first.')\n"
            "demo.add_step('Check', 'Run it, inspect the output, and improve one piece.')\n"
            "demo.run()\n"
        ),
        source_ids=[],
    )


def _fallback_diagram_suggestion(
    note: SectionNoteArtifact,
    synthesis_input: SectionSynthesisInput | None,
) -> DiagramSuggestion:
    elements = note.core_points[:4]
    if not elements:
        elements = [
            note.section_title,
            "Practical example",
            "Implementation step",
            "Expected result",
        ]

    diagram_type = (
        synthesis_input.suggested_diagram_type
        if synthesis_input and synthesis_input.suggested_diagram_type
        else "flowchart"
    )

    return DiagramSuggestion(
        diagram_type=diagram_type,
        title=f"{note.section_title}: visual map",
        description=(
            "A compact visual map showing the key idea, the practical action, "
            "and the result the reader should expect."
        ),
        elements=elements,
    )


def _note_is_assembly_ready(note: SectionNoteArtifact) -> bool:
    has_explanation = bool(note.central_thesis.strip()) and len(note.core_points) >= 2
    has_grounding = bool(
        note.supporting_facts
        or note.examples
        or note.code_snippets
        or note.implementation_steps
    )
    has_required_code = not note.must_include_code or bool(note.code_snippets)
    has_required_diagram = not note.must_include_diagram or bool(note.diagram_suggestions)
    return has_explanation and has_grounding and has_required_code and has_required_diagram


def normalize_section_note(
    note: SectionNoteArtifact,
    synthesis_input: SectionSynthesisInput | None = None,
) -> SectionNoteArtifact:
    """
    Normalize + enforce constraints on a synthesized section note.
    """

    allowed_ids = set(note.allowed_citation_source_ids or [])

    # --- core text fields ---
    note.core_points = _dedupe_preserve_order(note.core_points)[:MAX_CORE_POINTS]
    note.important_caveats = _dedupe_preserve_order(note.important_caveats)[
        :MAX_CAVEATS
    ]
    note.unresolved_gaps = _dedupe_preserve_order(note.unresolved_gaps)[
        :MAX_GAPS
    ]
    note.writer_guidance = _dedupe_preserve_order(note.writer_guidance)[
        :MAX_WRITER_GUIDANCE
    ]

    # --- supporting facts ---
    for fact in note.supporting_facts:
        fact.source_ids = _filter_allowed_source_ids(
            fact.source_ids, allowed_ids
        )
    note.supporting_facts = note.supporting_facts[:MAX_FACTS]

    # --- examples ---
    for ex in note.examples:
        ex.source_ids = _filter_allowed_source_ids(
            ex.source_ids, allowed_ids
        )
    note.examples = note.examples[:MAX_EXAMPLES]

    # --- flow steps ---
    note.recommended_flow = note.recommended_flow[:MAX_FLOW_STEPS]
    for i, step in enumerate(note.recommended_flow, start=1):
        step.step_number = i

    # --- source trace ---
    for trace in note.source_trace:
        trace.source_ids = _filter_allowed_source_ids(
            trace.source_ids, allowed_ids
        )

    # --- practical content guarantees ---
    if note.must_include_code and not note.code_snippets:
        note.code_snippets.append(_fallback_code_snippet(note))

    if note.must_include_diagram and not note.diagram_suggestions:
        note.diagram_suggestions.append(
            _fallback_diagram_suggestion(note, synthesis_input)
        )

    if synthesis_input is not None:
        if not note.book_state_summary:
            note.book_state_summary = synthesis_input.book_state_summary
        if not note.continuity_rules:
            note.continuity_rules = list(synthesis_input.continuity_rules)
        if not note.chapter_dependencies:
            note.chapter_dependencies = list(synthesis_input.chapter_dependencies)
        if note.implementation_strategy is None:
            note.implementation_strategy = synthesis_input.implementation_strategy
        if note.progression_strategy is None:
            note.progression_strategy = synthesis_input.progression_strategy
        if not note.book_contract:
            note.book_contract = dict(synthesis_input.book_contract)

    # --- source links for further reading ---
    if synthesis_input is not None and not note.reference_links:
        allowed_reference_ids = set(note.allowed_citation_source_ids or [])
        note.reference_links = [
            item
            for item in synthesis_input.source_references
            if item.source_id in allowed_reference_ids and item.url
        ][:MAX_REFERENCE_LINKS]
    else:
        note.reference_links = [
            item
            for item in note.reference_links
            if item.source_id in allowed_ids and item.url
        ][:MAX_REFERENCE_LINKS]

    # --- synthesis status correction ---
    if note.coverage_signal == CoverageSignal.WEAK:
        note.synthesis_status = SynthesisStatus.PARTIAL

    if note.coverage_signal == CoverageSignal.PARTIAL:
        if not note.unresolved_gaps:
            note.unresolved_gaps.append(
                "Some aspects of this section may be under-supported based on available research."
            )

    # A section can be usable for assembly while still preserving caveats about
    # incomplete source coverage. Reserve PARTIAL for weak or genuinely
    # under-built notes, otherwise the whole downstream pipeline looks failed.
    if (
        note.synthesis_status == SynthesisStatus.PARTIAL
        and note.coverage_signal == CoverageSignal.PARTIAL
        and _note_is_assembly_ready(note)
    ):
        note.synthesis_status = SynthesisStatus.READY

    return note
