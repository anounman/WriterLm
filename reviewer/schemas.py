from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ReviewStatus(str, Enum):
    APPROVED = "approved"
    REVISED = "revised"
    FLAGGED = "flagged"


class ReviewWarning(str, Enum):
    POSSIBLE_TOPIC_DRIFT = "possible_topic_drift"
    UNSUPPORTED_CLAIM_RISK = "unsupported_claim_risk"
    MISSING_CAVEAT = "missing_caveat"
    PARTIAL_UNCERTAINTY_WEAKENED = "partial_uncertainty_weakened"
    INVALID_CITATION_REMOVED = "invalid_citation_removed"
    CLEANUP_ARTIFACT_FIXED = "cleanup_artifact_fixed"
    MISSING_CODE_EXAMPLE = "missing_code_example"
    MISSING_DIAGRAM = "missing_diagram"
    PURE_TEXT_SECTION = "pure_text_section"
    SHALLOW_EXPLANATION = "shallow_explanation"
    MISSING_PRACTICAL_CONTENT = "missing_practical_content"
    PRIVATE_SOURCE_PATH_REMOVED = "private_source_path_removed"
    RAW_MARKUP_ARTIFACT = "raw_markup_artifact"
    UNRESOLVED_SELF_CORRECTION = "unresolved_self_correction"


class QualityScores(BaseModel):
    """Quality scores assigned by the reviewer to each section."""

    model_config = ConfigDict(extra="forbid")

    practicality_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="1-10: How practical/actionable is this section? 10 = reader can immediately apply what they learned.",
    )
    code_coverage_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="1-10: How well does code support the explanation? 10 = excellent code examples, well-commented.",
    )
    learning_depth_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="1-10: How deeply does the section teach? 10 = explains why, not just what, includes trade-offs.",
    )
    visual_richness_score: int = Field(
        ...,
        ge=1,
        le=10,
        description="1-10: Does the section use diagrams/visuals effectively? 10 = key concepts are visualized.",
    )
    source_grounding_score: int = Field(
        default=6,
        ge=1,
        le=10,
        description="1-10: Are important claims supported at the evidence level required by the Book Contract?",
    )
    continuity_score: int = Field(
        default=6,
        ge=1,
        le=10,
        description="1-10: Does this section preserve the book's thesis, terminology, examples, and progression?",
    )
    domain_fit_score: int = Field(
        default=6,
        ge=1,
        le=10,
        description="1-10: Does this section fit the contract's domain and avoid irrelevant validators or examples?",
    )


class ReviewerSectionInput(BaseModel):
    """
    Reviewer-facing section input assembled from Notes + Writer artifacts.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str
    section_title: str

    synthesis_status: str
    central_thesis: str
    core_points: List[str] = Field(default_factory=list)
    supporting_facts: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    important_caveats: List[str] = Field(default_factory=list)
    unresolved_gaps: List[str] = Field(default_factory=list)
    recommended_flow: List[str] = Field(default_factory=list)
    writer_guidance: List[str] = Field(default_factory=list)
    allowed_citation_source_ids: List[str] = Field(default_factory=list)

    # --- Content requirement flags ---
    must_include_code: bool = Field(default=False)
    must_include_diagram: bool = Field(default=False)
    book_contract: dict = Field(
        default_factory=dict,
        description="Persistent Book Contract used to choose domain-appropriate review checks.",
    )
    progression_strategy: Optional[str] = Field(default=None)

    writer_content: str
    writer_citations_used: List[str] = Field(default_factory=list)
    writer_code_blocks_count: int = Field(default=0)
    writer_diagram_hints_count: int = Field(default=0)
    writing_status: str


class ReviewerSectionOutput(BaseModel):
    """
    Final normalized reviewer result for one section.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str
    section_title: str
    reviewed_content: str
    review_status: ReviewStatus

    citations_used: List[str] = Field(default_factory=list)
    applied_changes_summary: List[str] = Field(default_factory=list)
    reviewer_warnings: List[ReviewWarning] = Field(default_factory=list)

    quality_scores: Optional[QualityScores] = Field(
        default=None,
        description="Quality scores for this section.",
    )


class ReviewerSectionResult(BaseModel):
    """
    Stored per-section artifact in the final review bundle.
    Includes both the structured input snapshot and the reviewer output.
    """

    model_config = ConfigDict(extra="forbid")

    section_input: ReviewerSectionInput
    section_output: ReviewerSectionOutput


class ReviewBundleMetadata(BaseModel):
    """
    Run-level metadata for the review bundle.
    """

    model_config = ConfigDict(extra="forbid")

    project_name: str = "book_generation"
    layer_name: str = "reviewer"
    total_sections: int
    approved_sections: int
    revised_sections: int
    flagged_sections: int

    avg_practicality_score: Optional[float] = None
    avg_code_coverage_score: Optional[float] = None
    avg_learning_depth_score: Optional[float] = None
    avg_visual_richness_score: Optional[float] = None


class ReviewBundle(BaseModel):
    """
    Final persisted artifact produced by the Reviewer layer.
    """

    model_config = ConfigDict(extra="forbid")

    metadata: ReviewBundleMetadata
    sections: List[ReviewerSectionResult] = Field(default_factory=list)
