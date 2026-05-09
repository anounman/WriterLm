from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


# -----------------------------
# Enums
# -----------------------------

class WritingStatus(str, Enum):
    """
    Final writing status for a section.

    Mirrors Synthesizer status but from a writing perspective.
    """

    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


# -----------------------------
# Core Input (from Synthesizer)
# -----------------------------

class WriterSectionInput(BaseModel):
    """
    Input to the Writer layer for a single section.

    This is derived directly from SectionNoteArtifact.
    Keep it explicit to avoid hidden coupling with previous layers.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str
    section_title: str

    synthesis_status: str  # keep flexible to match upstream enum

    central_thesis: str
    core_points: List[str]

    supporting_facts: List[dict] = Field(
        default_factory=list,
        description="Each item should include fact text + source_ids.",
    )

    examples: List[dict] = Field(
        default_factory=list,
        description="Each item should include example text + source_ids.",
    )

    # --- New fields for practical content ---
    code_snippets: List[dict] = Field(
        default_factory=list,
        description="Code snippets from synthesizer: {language, description, code, source_ids}.",
    )

    diagram_suggestions: List[dict] = Field(
        default_factory=list,
        description="Diagram suggestions: {diagram_type, title, description, elements}.",
    )

    implementation_steps: List[dict] = Field(
        default_factory=list,
        description="Implementation steps: {step_number, action, detail, has_code}.",
    )

    must_include_code: bool = Field(
        default=False,
        description="Whether the planner requires code in this section.",
    )
    must_include_diagram: bool = Field(
        default=False,
        description="Whether the planner requires a diagram in this section.",
    )

    important_caveats: List[str] = Field(default_factory=list)
    unresolved_gaps: List[str] = Field(default_factory=list)

    recommended_flow: List[dict] = Field(
        default_factory=list,
        description="Ordered steps describing how to structure the section.",
    )

    writer_guidance: List[str] = Field(default_factory=list)

    allowed_citation_source_ids: List[str] = Field(default_factory=list)
    reference_links: List[dict] = Field(
        default_factory=list,
        description="Reader-facing links: {source_id, title, url}.",
    )
    book_state_summary: str = Field(
        default="",
        description="Compact summary of the live book state this section must continue.",
    )
    continuity_rules: List[str] = Field(
        default_factory=list,
        description="Hard continuity rules and forbidden contradictions for this section.",
    )
    chapter_dependencies: List[str] = Field(
        default_factory=list,
        description="Specific earlier sections/examples that this section must build on.",
    )
    implementation_strategy: Optional[str] = Field(
        default=None,
        description="Chosen implementation/story strategy for the full manuscript.",
    )
    progression_strategy: Optional[str] = Field(
        default=None,
        description="Domain-neutral continuity strategy: argument, chronology, project, workflow, or learning sequence.",
    )
    book_contract: dict = Field(
        default_factory=dict,
        description="Persistent Book Contract used to adapt writing and validation.",
    )


# -----------------------------
# Output Per Section
# -----------------------------

class DiagramHint(BaseModel):
    """A LaTeX-friendly diagram hint embedded in the written output."""

    model_config = ConfigDict(extra="forbid")

    diagram_type: str = Field(
        ...,
        description="Type: flowchart, architecture, sequence_diagram, comparison_table, data_flow, graph.",
    )
    title: str = Field(..., description="Diagram title for the figure caption.")
    description: str = Field(..., description="What the diagram shows.")
    latex_label: Optional[str] = Field(
        default=None,
        description="LaTeX label for cross-referencing (e.g., fig:rag-pipeline).",
    )


class SectionDraft(BaseModel):
    """
    Final written output for one section.

    This is what Reviewer and Assembler will consume.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str
    section_title: str

    content: str = Field(
        ...,
        description="Final written section text in clean, natural language. Includes ```python code blocks and DIAGRAM: hints.",
    )

    citations_used: List[str] = Field(
        default_factory=list,
        description="Subset of allowed source_ids actually used in writing.",
    )

    diagram_hints: List[DiagramHint] = Field(
        default_factory=list,
        description="Structured diagram hints for LaTeX figure generation.",
    )

    code_blocks_count: int = Field(
        default=0,
        description="Number of code blocks included in the content.",
    )

    writing_status: WritingStatus


# -----------------------------
# Bundle Output
# -----------------------------

class WriterOutputBundle(BaseModel):
    """
    Final output of the Writer layer.

    Contains all section drafts.
    """

    model_config = ConfigDict(extra="forbid")

    section_drafts: List[SectionDraft]

    total_sections: int
    ready_sections: int
    partial_sections: int
    blocked_sections: int
