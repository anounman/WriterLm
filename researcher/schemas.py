from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


# =========================================================
# Enums
# =========================================================

class ResearchDepth(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


class QueryKind(str, Enum):
    CORE_CONCEPT = "core_concept"
    DEFINITION = "definition"
    EXAMPLE = "example"
    CASE_STUDY = "case_study"
    STATISTIC = "statistic"
    HISTORICAL = "historical"
    TECHNICAL = "technical"
    COUNTERPOINT = "counterpoint"
    RECENT_DEVELOPMENT = "recent_development"
    FOLLOW_UP = "follow_up"


class SourceType(str, Enum):
    WEBPAGE = "webpage"
    PDF = "pdf"
    BLOG = "blog"
    DOCS = "docs"
    RESEARCH_PAPER = "research_paper"
    NEWS = "news"
    REPORT = "report"
    UNKNOWN = "unknown"


class ExtractionMethod(str, Enum):
    TRAFILATURA = "trafilatura"
    PYMUPDF = "pymupdf"
    FIRECRAWL = "firecrawl"
    UNKNOWN = "unknown"


class EvidenceType(str, Enum):
    DEFINITION = "definition"
    FACT = "fact"
    EXAMPLE = "example"
    CASE_STUDY = "case_study"
    STATISTIC = "statistic"
    QUOTE = "quote"
    REFERENCE = "reference"
    CLAIM = "claim"
    INSIGHT = "insight"
    WARNING = "warning"


class CoverageStatus(str, Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class ReflexionAction(str, Enum):
    FINALIZE = "finalize"
    FOLLOW_UP = "follow_up"


# =========================================================
# Planner input references
# =========================================================

class PlannerSectionRef(BaseModel):
    section_id: str = Field(..., description="Stable section identifier from planner output.")
    chapter_id: str = Field(..., description="Parent chapter identifier.")
    chapter_title: str = Field(..., description="Parent chapter title.")
    section_title: str = Field(..., description="Section title from planner.")
    section_goal: str = Field(..., description="What this section is supposed to achieve.")
    section_summary: Optional[str] = Field(
        default=None,
        description="Optional short planner-produced summary for the section."
    )
    key_points: List[str] = Field(
        default_factory=list,
        description="Important section points already identified by the planner."
    )


# =========================================================
# Research task / brief
# =========================================================

class ResearchTask(BaseModel):
    task_id: str = Field(..., description="Stable id for this research task.")
    section: PlannerSectionRef
    depth: ResearchDepth = Field(
        default=ResearchDepth.STANDARD,
        description="Desired depth of research for this section."
    )
    objective: str = Field(..., description="Clear research objective for this section.")
    scope_inclusions: List[str] = Field(
        default_factory=list,
        description="Topics or angles that must be covered."
    )
    scope_exclusions: List[str] = Field(
        default_factory=list,
        description="Topics or angles intentionally excluded."
    )
    required_evidence_types: List[EvidenceType] = Field(
        default_factory=list,
        description="Evidence types that should appear in the final research packet."
    )
    research_questions: List[str] = Field(
        default_factory=list,
        description="Guiding questions that the researcher should answer."
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Any useful assumptions or framing constraints."
    )


# =========================================================
# Query planning
# =========================================================

class ResearchQuery(BaseModel):
    query_id: str = Field(..., description="Stable id for this query.")
    kind: QueryKind = Field(..., description="Why this query exists.")
    query_text: str = Field(..., description="Search query string.")
    rationale: str = Field(..., description="Short explanation for this query.")
    priority: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Relative importance. 1 = highest priority, 5 = lowest."
    )


class SearchPlan(BaseModel):
    task_id: str
    queries: List[ResearchQuery] = Field(default_factory=list)


# =========================================================
# Discovery / fetched source documents
# =========================================================

class DiscoveredSource(BaseModel):
    source_id: str = Field(..., description="Internal source id.")
    query_id: str = Field(..., description="Query that discovered this source.")
    title: str = Field(..., description="Search result title.")
    url: str = Field(..., description="Source URL.")
    snippet: Optional[str] = Field(default=None, description="Snippet from discovery layer.")
    source_type: SourceType = Field(default=SourceType.UNKNOWN)
    rank: int = Field(..., ge=1, description="Rank in the discovery result list.")
    discovery_score: Optional[float] = Field(
        default=None,
        description="Optional score from the search provider."
    )


class SourceDocument(BaseModel):
    source_id: str
    url: str
    title: str
    source_type: SourceType = Field(default=SourceType.UNKNOWN)
    extraction_method: ExtractionMethod = Field(default=ExtractionMethod.UNKNOWN)
    text: str = Field(..., description="Normalized extracted text.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata like author, date, domain, page count, etc."
    )
    extraction_success: bool = Field(default=True)
    extraction_error: Optional[str] = Field(default=None)


# =========================================================
# Source registry / provenance
# =========================================================

class SourceRegistryEntry(BaseModel):
    source_id: str
    url: str
    title: str
    source_type: SourceType = Field(default=SourceType.UNKNOWN)
    discovery_query_id: Optional[str] = None
    extraction_method: ExtractionMethod = Field(default=ExtractionMethod.UNKNOWN)
    content_hash: Optional[str] = Field(
        default=None,
        description="Hash of normalized extracted content for dedupe/provenance."
    )
    canonical_url: Optional[str] = Field(
        default=None,
        description="Normalized/canonical URL if available."
    )
    domain: Optional[str] = None
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reliability_notes: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(
        default_factory=list,
        description="Evidence items extracted from this source."
    )


# =========================================================
# Evidence extraction
# =========================================================

class EvidenceItem(BaseModel):
    evidence_id: str = Field(..., description="Stable evidence item id.")
    source_id: str = Field(..., description="Back-reference to source registry entry.")
    section_id: str = Field(..., description="Planner section id this evidence belongs to.")
    evidence_type: EvidenceType = Field(..., description="Type of evidence.")
    content: str = Field(..., description="Normalized extracted evidence content.")
    summary: Optional[str] = Field(
        default=None,
        description="Optional short explanation of why this evidence matters."
    )
    relevance_note: Optional[str] = Field(
        default=None,
        description="Why this evidence is relevant to the section objective."
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Model/system confidence in extraction quality."
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Optional concept labels for grouping later."
    )


class KnowledgeMapItem(BaseModel):
    label: str
    content: str
    supporting_source_ids: List[str] = Field(default_factory=list)
    source_reliability: Optional[str] = None
    source_freshness: Optional[str] = None
    uncertainty_flag: Optional[str] = None


class SectionKnowledgeMap(BaseModel):
    key_claims: List[KnowledgeMapItem] = Field(default_factory=list)
    definitions: List[KnowledgeMapItem] = Field(default_factory=list)
    examples: List[KnowledgeMapItem] = Field(default_factory=list)
    conflicting_viewpoints: List[KnowledgeMapItem] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    uncertainty_flags: List[str] = Field(default_factory=list)
    recommended_framing: List[str] = Field(default_factory=list)


# =========================================================
# Coverage / reflexion
# =========================================================

class CoverageReport(BaseModel):
    section_id: str
    status: CoverageStatus = Field(..., description="Overall coverage assessment.")
    covered_topics: List[str] = Field(default_factory=list)
    missing_topics: List[str] = Field(default_factory=list)
    weak_evidence_types: List[EvidenceType] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ReflexionDecision(BaseModel):
    section_id: str
    action: ReflexionAction = Field(..., description="Whether to finalize or continue.")
    reasoning: str = Field(..., description="Why this decision was made.")
    followup_queries: List[ResearchQuery] = Field(
        default_factory=list,
        description="Only populated when more research is needed."
    )
    max_additional_sources: int = Field(
        default=3,
        ge=0,
        description="Cap on follow-up expansion."
    )


# =========================================================
# Final research packet
# =========================================================

class SectionResearchPacket(BaseModel):
    packet_id: str = Field(..., description="Stable final packet id.")
    task_id: str = Field(..., description="Research task id.")
    section_id: str = Field(..., description="Planner section id.")
    chapter_id: str = Field(..., description="Planner chapter id.")
    section_title: str
    objective: str

    key_concepts: List[str] = Field(default_factory=list)
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    sources: List[SourceRegistryEntry] = Field(default_factory=list)
    knowledge_map: SectionKnowledgeMap = Field(
        default_factory=SectionKnowledgeMap,
        description=(
            "Source-grounded synthesis map for this section: key claims, supporting "
            "sources, reliability/freshness notes, definitions, examples, conflicts, "
            "open questions, uncertainty flags, and recommended framing."
        ),
    )

    coverage_report: Optional[CoverageReport] = None
    open_questions: List[str] = Field(default_factory=list)
    writing_guidance: List[str] = Field(
        default_factory=list,
        description="Hints for the next layer without writing the prose itself."
    )


# =========================================================
# Validation / node result helper models
# =========================================================

class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"] = "warning"


class ValidationReport(BaseModel):
    ok: bool = True
    issues: List[ValidationIssue] = Field(default_factory=list)
