from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from planner_agent.schemas import BookPlan
from quality.book_contract import BookContract, classify_book_contract
from quality.validator_registry import select_validators


DIAGRAM_RE = re.compile(r"(?im)^DIAGRAM:\s*(.+)$")
HEADING_RE = re.compile(r"(?im)^#{2,4}\s+(.+?)\s*$")
TERM_RE = re.compile(r"\b[A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,3}\b")


class SectionStateEntry(BaseModel):
    section_id: str
    section_title: str
    chapter_purpose: str = ""
    summary: str = ""
    terminology: list[str] = Field(default_factory=list)
    examples_used: list[str] = Field(default_factory=list)
    diagrams_created: list[str] = Field(default_factory=list)
    citations_used: list[str] = Field(default_factory=list)
    claims_made: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class BookState(BaseModel):
    title: str
    book_contract: Optional[BookContract] = None
    thesis: str
    target_audience: str
    expected_depth: str
    pedagogy_style: str
    running_project: Optional[str] = None
    progression_strategy: str = "single coherent progression"
    implementation_strategy: str = "not-applicable-unless-the-contract-requires-implementation"
    terminology: list[str] = Field(default_factory=list)
    terminology_definitions: dict[str, str] = Field(default_factory=dict)
    style_conventions: list[str] = Field(default_factory=list)
    notation_conventions: list[str] = Field(default_factory=list)
    example_conventions: list[str] = Field(default_factory=list)
    examples_used: list[str] = Field(default_factory=list)
    claims_made: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    unresolved_assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    argument_progression: list[str] = Field(default_factory=list)
    narrative_progression: list[str] = Field(default_factory=list)
    pedagogical_progression: list[str] = Field(default_factory=list)
    forbidden_contradictions: list[str] = Field(default_factory=list)
    source_map: dict[str, list[str]] = Field(default_factory=dict)
    chapter_dependencies: dict[str, list[str]] = Field(default_factory=dict)
    diagrams_created: list[str] = Field(default_factory=list)
    tables_created: list[str] = Field(default_factory=list)
    case_studies: list[str] = Field(default_factory=list)
    domain_specific_constraints: list[str] = Field(default_factory=list)
    running_project_state: dict[str, str] = Field(default_factory=dict)
    evidence_map: dict[str, list[str]] = Field(default_factory=dict)
    action_model: list[str] = Field(default_factory=list)
    learning_objectives: dict[str, list[str]] = Field(default_factory=dict)
    prerequisite_concepts: list[str] = Field(default_factory=list)
    section_history: list[SectionStateEntry] = Field(default_factory=list)


def build_initial_book_state(
    *,
    book_plan: BookPlan,
    planner_input: dict[str, Any],
    research_bundle_payload: dict[str, Any] | None = None,
) -> BookState:
    contract = classify_book_contract(planner_input, book_plan)
    activations = select_validators(contract)
    contract.activated_validators = [item.name for item in activations]
    contract.validator_rationales = {item.name: item.reason for item in activations}

    pedagogy_style = str(planner_input.get("pedagogy_style") or "auto")
    theory_practice_balance = str(planner_input.get("theory_practice_balance") or "balanced")
    book_type = str(planner_input.get("book_type") or "auto")
    running_project = book_plan.running_project or planner_input.get("running_project_description")

    thesis_parts = [
        str(planner_input.get("topic") or book_plan.title),
        f"for {planner_input.get('audience') or book_plan.audience}",
        f"with {theory_practice_balance.replace('_', ' ')} emphasis",
    ]
    thesis = " ".join(part.strip() for part in thesis_parts if part).strip()

    progression_strategy = _infer_progression_strategy(contract)
    implementation_strategy = _infer_implementation_strategy(contract, planner_input, book_plan)
    style_conventions = [
        f"Honor the Book Contract domain: {contract.domain}.",
        f"Honor the Book Contract book type: {contract.book_type}.",
        f"Honor the requested book type: {book_type}.",
        f"Honor the requested pedagogy style: {contract.pedagogy_style if pedagogy_style == 'auto' else pedagogy_style}.",
        f"Honor the requested depth: {contract.expected_depth or book_plan.depth}.",
        "Do not silently switch notation, tooling, source standards, or narrative structure between chapters.",
    ]
    example_conventions = [
        contract.examples_strategy,
        "Reuse earlier examples, cases, arguments, timelines, workflows, or projects when doing so strengthens continuity.",
        "When the contract is project-based, each later chapter should build on the same project state.",
    ]
    notation_conventions = [
        contract.terminology_policy,
        "Keep terminology stable once introduced.",
        "Avoid introducing new aliases for the same concept unless you explicitly explain the mapping.",
    ]
    forbidden_contradictions = [
        "Do not contradict earlier definitions, assumptions, claims, chronology, procedures, or implementation choices.",
        "Do not downgrade the audience depth from the original request.",
        "Do not abandon the running project, argument, chronology, case, workflow, or learning sequence unless the outline explicitly closes it.",
        "Do not force programming/code language into non-technical books.",
    ]
    forbidden_contradictions.extend(contract.must_not_do)

    source_map = _build_source_map(research_bundle_payload)
    chapter_dependencies = _build_chapter_dependencies(book_plan)

    return BookState(
        title=book_plan.title,
        book_contract=contract,
        thesis=thesis,
        target_audience=book_plan.audience,
        expected_depth=book_plan.depth,
        pedagogy_style=contract.pedagogy_style if pedagogy_style == "auto" else pedagogy_style,
        running_project=running_project,
        progression_strategy=progression_strategy,
        implementation_strategy=implementation_strategy,
        style_conventions=style_conventions,
        notation_conventions=notation_conventions,
        example_conventions=example_conventions,
        unresolved_assumptions=_clean_list(planner_input.get("goals") or []),
        forbidden_contradictions=forbidden_contradictions,
        source_map=source_map,
        chapter_dependencies=chapter_dependencies,
        domain_specific_constraints=contract.domain_constraints,
        evidence_map=source_map,
        action_model=_infer_action_model(contract),
        learning_objectives=_build_learning_objectives(book_plan),
        prerequisite_concepts=_infer_prerequisites(book_plan),
    )


def build_section_context(
    *,
    book_state: BookState,
    section_id: str,
    section_title: str,
    chapter_title: str,
) -> dict[str, Any]:
    previous_sections = book_state.section_history[-3:]
    prior_text = [
        f"{entry.section_title}: {entry.summary}".strip(": ")
        for entry in previous_sections
        if entry.summary
    ]
    context_lines = [
        f"Book thesis: {book_state.thesis}",
        f"Audience: {book_state.target_audience}",
        f"Depth: {book_state.expected_depth}",
        f"Pedagogy style: {book_state.pedagogy_style}",
        f"Progression strategy: {book_state.progression_strategy}",
        f"Implementation strategy: {book_state.implementation_strategy}",
    ]
    if book_state.book_contract is not None:
        context_lines.append("Book Contract:\n" + book_state.book_contract.compact_context())
    if book_state.running_project:
        context_lines.append(f"Running project/example: {book_state.running_project}")
    if book_state.terminology:
        context_lines.append("Established terminology: " + ", ".join(book_state.terminology[:12]))
    if book_state.claims_made:
        context_lines.append("Earlier claims to preserve or avoid contradicting: " + " | ".join(book_state.claims_made[-5:]))
    if previous_sections:
        context_lines.append("Most recent section continuity:")
        context_lines.extend(f"- {line}" for line in prior_text[:3])
    dependencies = book_state.chapter_dependencies.get(section_id) or book_state.chapter_dependencies.get(chapter_title) or []
    if dependencies:
        context_lines.append("This section builds on: " + ", ".join(dependencies[:5]))

    return {
        "book_state_summary": "\n".join(context_lines),
        "continuity_rules": list(book_state.forbidden_contradictions + book_state.style_conventions + book_state.notation_conventions),
        "chapter_dependencies": dependencies,
        "implementation_strategy": book_state.implementation_strategy,
        "progression_strategy": book_state.progression_strategy,
        "pedagogy_style": book_state.pedagogy_style,
        "book_contract": book_state.book_contract.model_dump(mode="json") if book_state.book_contract else {},
    }


def update_book_state_from_reviewed_section(
    *,
    book_state: BookState,
    section_id: str,
    section_title: str,
    reviewed_content: str,
    citations_used: list[str] | None = None,
) -> BookState:
    headings = [match.group(1).strip() for match in HEADING_RE.finditer(reviewed_content)]
    diagrams = [match.group(1).strip() for match in DIAGRAM_RE.finditer(reviewed_content)]
    terminology = _pick_terms(reviewed_content)
    summary = _summarize_section(reviewed_content)
    claims = _pick_claims(reviewed_content)

    book_state.terminology = _merge_unique(book_state.terminology, terminology)[:40]
    book_state.claims_made = _merge_unique(book_state.claims_made, claims)[:80]
    book_state.examples_used = _merge_unique(book_state.examples_used, headings[:5])[:80]
    book_state.sources_used = _merge_unique(book_state.sources_used, citations_used or [])[:120]
    book_state.diagrams_created = _merge_unique(book_state.diagrams_created, diagrams)
    book_state.section_history.append(
        SectionStateEntry(
            section_id=section_id,
            section_title=section_title,
            summary=summary,
            terminology=terminology,
            examples_used=headings[:5],
            diagrams_created=diagrams,
            citations_used=list(citations_used or []),
            claims_made=claims,
        )
    )
    return book_state


def write_book_state(path: Path, book_state: BookState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(book_state.model_dump_json(indent=2), encoding="utf-8")


def load_book_state(path: Path) -> BookState:
    return BookState.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _infer_progression_strategy(contract: BookContract) -> str:
    if contract.book_type == "project_based_book":
        return "one cumulative project or scenario"
    if contract.book_type in {"textbook", "exam_prep"}:
        return "learning objectives, prerequisite concepts, worked examples, and practice"
    if contract.book_type in {"practical_handbook", "implementation_manual"}:
        return "reader workflow, decisions, cautions, and applied examples"
    if contract.domain == "philosophy":
        return "argument map with definitions, objections, and responses"
    if contract.domain == "history":
        return "chronology with context, evidence, interpretation, and consequences"
    if contract.book_type == "research_survey":
        return "evidence map with competing viewpoints and uncertainty"
    return "single coherent concept progression"


def _infer_implementation_strategy(contract: BookContract, planner_input: dict[str, Any], book_plan: BookPlan) -> str:
    if not contract.profile.implementation_heavy and not contract.profile.code_validation_needed:
        return "not-applicable-unless-the-contract-requires-implementation"
    corpus = " ".join(
        [
            str(planner_input.get("topic") or ""),
            str(planner_input.get("running_project_description") or ""),
            book_plan.title,
            book_plan.running_project or "",
        ]
    ).lower()
    if "terraform" in corpus:
        return "Terraform"
    if "cloudformation" in corpus:
        return "CloudFormation"
    if "cdk" in corpus:
        return "AWS CDK"
    if any(keyword in corpus for keyword in ("python", "pandas", "notebook")):
        return "Python"
    if any(keyword in corpus for keyword in ("typescript", "node", "react", "javascript")):
        return "TypeScript/JavaScript"
    if any(keyword in corpus for keyword in ("math", "algebra", "proof", "theorem")):
        return "Textbook-style mathematical exposition"
    if contract.book_type in {"practical_handbook", "implementation_manual"}:
        return "single consistent reader workflow"
    return "single-consistent-strategy"


def _infer_action_model(contract: BookContract) -> list[str]:
    if contract.book_type in {"practical_handbook", "implementation_manual"}:
        return ["recognize situation", "choose approach", "apply steps", "check result", "adjust safely"]
    if contract.book_type == "project_based_book":
        return ["set up shared scenario", "advance artifact", "validate progress", "integrate final outcome"]
    return []


def _build_learning_objectives(book_plan: BookPlan) -> dict[str, list[str]]:
    objectives: dict[str, list[str]] = {}
    for chapter in book_plan.chapters:
        objectives[chapter.title] = [section.goal for section in chapter.sections if section.goal][:8]
    return objectives


def _infer_prerequisites(book_plan: BookPlan) -> list[str]:
    first_chapter = book_plan.chapters[0] if book_plan.chapters else None
    if first_chapter is None:
        return []
    terms: list[str] = []
    for section in first_chapter.sections[:3]:
        terms.extend(section.key_questions[:2])
    return _merge_unique([], terms)[:8]


def _build_source_map(research_bundle_payload: dict[str, Any] | None) -> dict[str, list[str]]:
    source_map: dict[str, list[str]] = {}
    if not isinstance(research_bundle_payload, dict):
        return source_map

    for chapter in research_bundle_payload.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for packet in chapter.get("section_packets") or []:
            if not isinstance(packet, dict):
                continue
            section_id = str(packet.get("section_id") or "")
            refs = packet.get("source_references") or packet.get("sources") or []
            urls = []
            if isinstance(refs, list):
                for item in refs:
                    if isinstance(item, dict) and item.get("url"):
                        urls.append(str(item["url"]))
            if section_id and urls:
                source_map[section_id] = urls[:8]
    return source_map


def _build_chapter_dependencies(book_plan: BookPlan) -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    seen_sections: list[str] = []
    for chapter in book_plan.chapters:
        chapter_seen = [section.title for section in chapter.sections]
        for section in chapter.sections:
            deps = []
            if section.builds_on:
                deps.append(section.builds_on)
            deps.extend(seen_sections[-3:])
            dependencies[section.title] = _merge_unique([], deps)
            section_id = f"chapter-{chapter.chapter_number}-section-{_slugify(section.title)}"
            dependencies[section_id] = list(dependencies[section.title])
        seen_sections.extend(chapter_seen)
    return dependencies


def _pick_terms(content: str) -> list[str]:
    return _merge_unique([], [match.group(0).strip() for match in TERM_RE.finditer(content)])[:15]


def _summarize_section(content: str) -> str:
    clean = re.sub(r"```[\s\S]*?```", "", content)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) <= 240:
        return clean
    return clean[:237].rstrip() + "..."


def _pick_claims(content: str) -> list[str]:
    clean = re.sub(r"```[\s\S]*?```", "", content)
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    signals = re.compile(r"\b(?:is|are|was|were|causes|shows|means|requires|should|must|because|therefore)\b", re.IGNORECASE)
    return [sentence.strip()[:220] for sentence in sentences if len(sentence.strip()) > 45 and signals.search(sentence)][:8]


def _merge_unique(existing: list[str], new_items: list[str]) -> list[str]:
    merged = list(existing)
    seen = {item.casefold() for item in merged}
    for item in new_items:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return merged


def _clean_list(values: list[Any]) -> list[str]:
    output = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned:
            output.append(cleaned)
    return output


def _slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in cleaned.split("-") if part) or "untitled"
