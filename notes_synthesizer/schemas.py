from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


class CoverageSignal(str, Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    WEAK = "weak"


class SynthesisStatus(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class SourceTraceItem(BaseModel):
    """
    Lightweight traceability record showing which existing source IDs
    support a synthesized note element.
    """

    model_config = ConfigDict(extra="forbid")

    note_element: str = Field(
        ...,
        description="Name of the synthesized element being supported, e.g. 'core_point_1'.",
    )
    source_ids: List[str] = Field(
        default_factory=list,
        description="Subset of source IDs already present in the research packet.",
    )

    @field_validator("source_ids")
    @classmethod
    def dedupe_source_ids(cls, value: List[str]) -> List[str]:
        seen = set()
        deduped = []
        for item in value:
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped


class SourceReference(BaseModel):
    """Compact source link carried forward for further-reading lists."""

    model_config = ConfigDict(extra="ignore")

    source_id: str = Field(..., min_length=1)
    title: str = Field(default="")
    url: str = Field(default="")


class SupportingFact(BaseModel):
    """
    Compact factual statement the writer may use as grounded support.
    """

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(
        ...,
        min_length=1,
        description="Concise factual support statement.",
    )
    source_ids: List[str] = Field(
        default_factory=list,
        description="Allowed supporting source IDs from the research artifact only.",
    )

    @field_validator("source_ids")
    @classmethod
    def dedupe_source_ids(cls, value: List[str]) -> List[str]:
        seen = set()
        deduped = []
        for item in value:
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped


class ExampleNote(BaseModel):
    """
    Strong example or illustration that helps the writer explain the section.
    """

    model_config = ConfigDict(extra="forbid")

    example: str = Field(
        ...,
        min_length=1,
        description="Compact example or illustrative case.",
    )
    source_ids: List[str] = Field(
        default_factory=list,
        description="Allowed supporting source IDs from the research artifact only.",
    )

    @field_validator("source_ids")
    @classmethod
    def dedupe_source_ids(cls, value: List[str]) -> List[str]:
        seen = set()
        deduped = []
        for item in value:
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped


class FlowStep(BaseModel):
    """
    Recommended local writing flow for the section.
    """

    model_config = ConfigDict(extra="forbid")

    step_number: int = Field(
        ...,
        ge=1,
        description="Ordered flow step.",
    )
    instruction: str = Field(
        ...,
        min_length=1,
        description="What the writer should do in this step.",
    )


class SectionSynthesisInput(BaseModel):
    """
    Compact, token-efficient input created from planner metadata and
    researcher artifacts. This is the object sent to the synthesizer LLM call.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(..., min_length=1)
    section_title: str = Field(..., min_length=1)
    section_objective: str = Field(..., min_length=1)

    planner_context: Optional[str] = Field(
        default=None,
        description="Optional short planner-derived context for this section.",
    )

    key_concepts: List[str] = Field(default_factory=list)
    evidence_items: List[str] = Field(
        default_factory=list,
        description="Compressed evidence statements, not raw source text.",
    )
    writing_guidance: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)

    coverage_signal: CoverageSignal = Field(
        ...,
        description="Normalized research coverage strength.",
    )

    available_source_ids: List[str] = Field(
        default_factory=list,
        description="All source IDs allowed for downstream citation usage.",
    )
    source_references: List[SourceReference] = Field(
        default_factory=list,
        description="Compact source metadata for links/further reading.",
    )

    # --- Content requirement flags from planner ---
    must_include_code: bool = Field(
        default=False,
        description="Whether the planner requires code in this section.",
    )
    must_include_diagram: bool = Field(
        default=False,
        description="Whether the planner requires a diagram in this section.",
    )
    suggested_diagram_type: Optional[str] = Field(
        default=None,
        description="Planner hint for diagram type.",
    )
    book_state_summary: str = Field(
        default="",
        description="Compact summary of the live manuscript state that this section should continue.",
    )
    continuity_rules: List[str] = Field(
        default_factory=list,
        description="Hard continuity rules and forbidden contradictions for this section.",
    )
    chapter_dependencies: List[str] = Field(
        default_factory=list,
        description="Specific earlier concepts, sections, or milestones this section should build on.",
    )
    implementation_strategy: Optional[str] = Field(
        default=None,
        description="Chosen implementation/story strategy for the whole book.",
    )
    progression_strategy: Optional[str] = Field(
        default=None,
        description="Domain-neutral continuity strategy: argument, chronology, project, workflow, or learning sequence.",
    )
    book_contract: dict = Field(
        default_factory=dict,
        description="Persistent Book Contract used to adapt research, writing, validation, and repair to this topic.",
    )

    @field_validator("key_concepts", "evidence_items", "writing_guidance", "open_questions", "available_source_ids")
    @classmethod
    def strip_and_remove_empty(cls, value: List[str]) -> List[str]:
        cleaned = []
        seen = set()
        for item in value:
            if not item:
                continue
            normalized = item.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)
        return cleaned


class CodeSnippet(BaseModel):
    """A code snippet extracted from research or synthesized for the section."""

    model_config = ConfigDict(extra="forbid")

    language: str = Field(
        default="python",
        description="Programming language of the snippet.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="What this code demonstrates.",
    )
    code: str = Field(
        ...,
        min_length=1,
        description="The actual code content.",
    )
    source_ids: List[str] = Field(
        default_factory=list,
        description="Source IDs this code is derived from.",
    )


class DiagramSuggestion(BaseModel):
    """A diagram or visualization the writer should produce for this section."""

    model_config = ConfigDict(extra="forbid")

    diagram_type: str = Field(
        ...,
        description="Type: flowchart, architecture, sequence_diagram, comparison_table, data_flow, graph.",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Short title for the diagram.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="What the diagram should show.",
    )
    elements: List[str] = Field(
        default_factory=list,
        description="Key elements/nodes/columns the diagram should contain.",
    )


class ImplementationStep(BaseModel):
    """A concrete implementation step the reader should follow."""

    model_config = ConfigDict(extra="forbid")

    step_number: int = Field(..., ge=1)
    action: str = Field(
        ...,
        min_length=1,
        description="What to do (e.g., 'Install dependencies', 'Create the retriever class').",
    )
    detail: str = Field(
        default="",
        description="Additional detail or explanation for this step.",
    )
    has_code: bool = Field(
        default=False,
        description="Whether this step involves writing code.",
    )


class SectionNoteArtifact(BaseModel):
    """
    Final compact, writer-ready note object for one section.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(..., min_length=1)
    section_title: str = Field(..., min_length=1)
    section_objective: str = Field(..., min_length=1)

    synthesis_status: SynthesisStatus = Field(...)
    coverage_signal: CoverageSignal = Field(...)

    central_thesis: str = Field(
        ...,
        min_length=1,
        description="The main claim or framing for the section.",
    )

    core_points: List[str] = Field(
        default_factory=list,
        description="Primary points the writer should cover.",
    )

    supporting_facts: List[SupportingFact] = Field(default_factory=list)
    examples: List[ExampleNote] = Field(default_factory=list)

    # --- New fields for practical book generation ---
    code_snippets: List[CodeSnippet] = Field(
        default_factory=list,
        description="Code snippets the writer should include or adapt.",
    )
    diagram_suggestions: List[DiagramSuggestion] = Field(
        default_factory=list,
        description="Diagrams the writer should produce for this section.",
    )
    implementation_steps: List[ImplementationStep] = Field(
        default_factory=list,
        description="Step-by-step implementation guide for the reader.",
    )

    # --- Content requirement flags (passed from planner) ---
    must_include_code: bool = Field(
        default=False,
        description="Whether the planner requires code in this section.",
    )
    must_include_diagram: bool = Field(
        default=False,
        description="Whether the planner requires a diagram in this section.",
    )

    important_caveats: List[str] = Field(
        default_factory=list,
        description="Nuances, limits, and warnings that must be preserved.",
    )
    unresolved_gaps: List[str] = Field(
        default_factory=list,
        description="What remains uncertain or under-supported.",
    )

    recommended_flow: List[FlowStep] = Field(default_factory=list)
    writer_guidance: List[str] = Field(default_factory=list)

    allowed_citation_source_ids: List[str] = Field(
        default_factory=list,
        description="Whitelisted source IDs the writer may cite from this section note.",
    )

    source_trace: List[SourceTraceItem] = Field(
        default_factory=list,
        description="Minimal traceability from note elements to source IDs.",
    )
    reference_links: List[SourceReference] = Field(
        default_factory=list,
        description="Best source links the writer can include as further reading.",
    )
    book_state_summary: str = Field(
        default="",
        description="The book state summary this section was generated against.",
    )
    continuity_rules: List[str] = Field(
        default_factory=list,
        description="Continuity rules the downstream writer must preserve.",
    )
    chapter_dependencies: List[str] = Field(
        default_factory=list,
        description="Earlier chapters/sections/examples this section should explicitly build on.",
    )
    implementation_strategy: Optional[str] = Field(
        default=None,
        description="Chosen implementation/story strategy for the full manuscript.",
    )
    progression_strategy: Optional[str] = Field(
        default=None,
        description="Domain-neutral continuity strategy for the full manuscript.",
    )
    book_contract: dict = Field(
        default_factory=dict,
        description="Persistent Book Contract used to adapt writing and validation.",
    )

    @field_validator(
        "core_points",
        "important_caveats",
        "unresolved_gaps",
        "writer_guidance",
        "allowed_citation_source_ids",
        "continuity_rules",
        "chapter_dependencies",
    )
    @classmethod
    def strip_and_remove_empty(cls, value: List[str]) -> List[str]:
        cleaned = []
        seen = set()
        for item in value:
            if not item:
                continue
            normalized = item.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)
        return cleaned


class NotesSynthesisBundle(BaseModel):
    """
    Final bundle emitted by the Notes Synthesizer layer and consumed by the Writer.
    """

    model_config = ConfigDict(extra="forbid")

    section_notes: List[SectionNoteArtifact] = Field(default_factory=list)
    total_sections: int = Field(..., ge=0)
    ready_sections: int = Field(..., ge=0)
    partial_sections: int = Field(..., ge=0)
    blocked_sections: int = Field(..., ge=0)
