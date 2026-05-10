from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


ApiKeyProvider = Literal["google", "groq", "tavily", "firecrawl"]
Provider = Literal["google", "groq"]
Density = Literal["high", "medium", "low"]
CodeDensity = Literal["none", "high", "medium", "low"]
LatexEngine = Literal["pdflatex", "xelatex", "lualatex"]
BookType = Literal[
    "auto",
    "textbook",
    "practice_workbook",
    "course_companion",
    "implementation_guide",
    "reference_handbook",
    "conceptual_guide",
    "exam_prep",
]
TheoryPracticeBalance = Literal["auto", "theory_heavy", "balanced", "practice_heavy", "implementation_heavy"]
PedagogyStyle = Literal[
    "auto",
    "german_theoretical",
    "indian_theory_then_examples",
    "socratic",
    "exam_oriented",
    "project_based",
]
SourceUsage = Literal["auto", "primary_curriculum", "supplemental", "example_inspiration"]
ExerciseStrategy = Literal["auto", "none", "extract_patterns", "worked_examples", "practice_sets"]


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Use plain `str` instead of `EmailStr` because Clerk generates synthetic
    # placeholder addresses (e.g. user-xxx@clerk-user.local) for OAuth users
    # who have no verified primary email.  Those fail Pydantic's strict RFC
    # 5322 domain validation even though they are perfectly valid DB values.
    email: str
    created_at: datetime


class ApiKeyUpsert(BaseModel):
    provider: ApiKeyProvider
    value: str = Field(..., min_length=3)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: ApiKeyProvider
    key_hint: str
    created_at: datetime
    updated_at: datetime


class PipelineConfig(BaseModel):
    llm_provider: Provider = "google"
    planner_google_model: str = "gemini-2.5-flash-lite"
    researcher_google_model: str = "gemini-2.5-flash-lite"
    notes_google_model: str = "gemini-2.5-flash-lite"
    writer_google_model: str = "gemini-2.5-flash-lite"
    reviewer_google_model: str = "gemini-2.5-flash-lite"
    planner_groq_model: str = "openai/gpt-oss-120b"
    researcher_groq_model: str = "openai/gpt-oss-120b"
    notes_groq_model: str = "llama-3.3-70b-versatile"
    writer_groq_model: str = "llama-3.3-70b-versatile"
    reviewer_groq_model: str = "openai/gpt-oss-120b"
    parallel_section_pipeline: bool = True
    section_pipeline_concurrency: int = Field(default=2, ge=1, le=12)
    compile_latex: bool = True
    strict_latex_compile: bool = False
    latex_engine: LatexEngine = "pdflatex"
    research_execution_profile: Literal["budget", "debug", "full"] = "budget"
    token_budget: int | None = Field(default=None, ge=1000)
    max_completion_tokens: int | None = Field(default=None, ge=256)
    image_assets_enabled: bool = True
    web_image_search_enabled: bool = True
    generated_images_enabled: bool = True
    image_generation_model: str = "gemini-2.5-flash-image"
    max_image_assets: int = Field(default=4, ge=0, le=24)


DepthLevel = Literal["surface", "intermediate", "deep", "exhaustive"]
ImplementationStyle = Literal[
    "conceptual_only",
    "pseudocode",
    "recipe_steps",
    "file_by_file",
    "project_progressive",
    "argument_driven",
    "case_study_playbook",
    "workbook",
    "visual_textbook",
    "reference",
]
SectionStyle = Literal[
    "academic",
    "conversational",
    "handbook",
    "tutorial",
    "reference",
    "file_by_file_implementation",
    "academic_argument",
    "case_study_playbook",
    "visual_textbook",
    "workbook",
]
CodeArtifactPolicy = Literal[
    "no_code",
    "pseudocode_only",
    "minimal_runnable",
    "file_labeled_code_required",
]
DiagramStyle = Literal[
    "none",
    "conceptual",
    "architecture",
    "data_flow",
    "comparison_matrix",
    "architecture_sequence_schema_deployment",
    "concept_maps_decision_trees_checklists",
    "argument_maps_comparison_matrices",
    "timelines_cause_effect_maps",
    "frameworks_matrices_funnels",
]
SourceStrictness = Literal["low", "medium", "high", "primary_sources_required"]
EvidenceStandard = Literal["anecdotal", "curated", "primary_source", "peer_reviewed"]


class GenerationContract(BaseModel):
    """Rich generation directives that travel with the request through the entire pipeline.

    All fields are optional — the deterministic normalization layer fills defaults
    based on the topic, audience, and book-type when the LLM parser or the user
    does not supply them.
    """

    depth_level: DepthLevel | None = Field(
        default=None,
        description="How deep the content should go: surface (overview), intermediate (working knowledge), deep (expert), exhaustive (reference-grade).",
    )
    implementation_style: ImplementationStyle | None = Field(
        default=None,
        description="Controls how practical/implementation content is structured.",
    )
    section_style: SectionStyle | None = Field(
        default=None,
        description="The prose style for each section.",
    )
    code_artifact_policy: CodeArtifactPolicy | None = Field(
        default=None,
        description="Explicit policy for code in the book. Overrides code_density when set.",
    )
    diagram_style: DiagramStyle | None = Field(
        default=None,
        description="Preferred diagram type when diagrams are included.",
    )
    source_strictness: SourceStrictness | None = Field(
        default=None,
        description="How strictly sources must be validated and attributed.",
    )
    evidence_standard: EvidenceStandard | None = Field(
        default=None,
        description="Minimum evidence standard for claims in the book.",
    )
    showcase_candidate: bool = Field(
        default=False,
        description="When True, the book is intended as a polished showcase piece with higher quality thresholds.",
    )
    required_stack: list[str] = Field(
        default_factory=list,
        description="Technologies that code examples MUST use (e.g. ['Python', 'FastAPI', 'PostgreSQL']).",
    )
    forbidden_content: list[str] = Field(
        default_factory=list,
        description="Topics or content types that MUST NOT appear (e.g. ['clinical diagnosis', 'fake quotes']).",
    )
    project_artifacts: list[str] = Field(
        default_factory=list,
        description="Expected project deliverables (e.g. ['folder tree', 'source files', 'tests', 'Dockerfile']).",
    )
    required_outputs: list[str] = Field(
        default_factory=list,
        description="Output types every section should produce when applicable (e.g. ['definitions', 'exercises']).",
    )
    success_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria the final book must meet (e.g. ['homepage showcase-ready', 'no generic filler']).",
    )
    running_examples: list[str] = Field(
        default_factory=list,
        description="Running examples or case studies that persist across chapters.",
    )
    style_references: list[str] = Field(
        default_factory=list,
        description="Books or resources whose style the user wants to emulate.",
    )
    target_reader_outcome: str | None = Field(
        default=None,
        description="What the reader should be able to do after finishing the book.",
    )
    citation_policy: str | None = Field(
        default=None,
        description="How citations and attributions should be handled.",
    )
    visual_policy: str | None = Field(
        default=None,
        description="Policy for diagrams, charts, and visual elements.",
    )
    notation_system: str | None = Field(
        default=None,
        description="Preferred notation system (e.g. 'LaTeX', 'standard mathematical', 'UML').",
    )


class BookRequest(BaseModel):
    topic: str = Field(..., min_length=3)
    audience: str = Field(..., min_length=3)
    tone: str = "clear and supportive"
    book_type: BookType = "auto"
    theory_practice_balance: TheoryPracticeBalance = "balanced"
    pedagogy_style: PedagogyStyle = "auto"
    source_usage: SourceUsage = "auto"
    exercise_strategy: ExerciseStrategy = "auto"
    goals: list[str] = Field(default_factory=list)
    project_based: bool = False
    running_project_description: str | None = None
    code_density: CodeDensity = "none"
    example_density: Density = "high"
    diagram_density: Density = "medium"
    generation_contract: GenerationContract | None = Field(
        default=None,
        description="Optional rich generation directives. Normalization fills defaults when missing.",
    )
    max_section_words: int | None = Field(default=None, ge=150, le=2000)
    force_web_research: bool = Field(
        default=False,
        description="When True, run web research even if user PDFs are present (combined mode).",
    )
    urls: list[str] = Field(
        default_factory=list,
        description="Optional user-provided source URLs to include in web research.",
    )
    language_request: str | None = Field(
        default=None,
        description=(
            "Free-form language instruction injected into the planner prompt. "
            "Examples: 'Explain all theory in English, but write exercise solutions and exam formulas in German.' "
            "'Use French for all content.' "
            "'Bilingual: English explanations, German technical terms and exam answers.'"
        ),
    )
    target_quality_score: int = Field(
        default=75,
        ge=0,
        le=100,
        description="Minimum target score before the job can be marked as cleanly completed.",
    )
    max_repair_passes: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum automatic quality repair passes before final status is chosen.",
    )
    hard_fail_threshold: int = Field(
        default=45,
        ge=0,
        le=100,
        description="Scores below this threshold are major quality issues, not plain completion.",
    )
    auto_repair: bool = Field(
        default=True,
        description="Automatically repair low-quality output before final assembly/completion.",
    )
    sample_first: bool = Field(
        default=False,
        description="Validate an early sample section before generating or accepting a full manuscript.",
    )
    quality_mode: Literal["fast_draft", "full_generation", "full_auto_repair", "sample_first"] = "full_auto_repair"


class QualityEstimateRequest(BaseModel):
    request: BookRequest


class RepairRequest(BaseModel):
    target_quality_score: int | None = Field(default=None, ge=0, le=100)
    max_repair_passes: int | None = Field(default=None, ge=0, le=5)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    current_stage: str
    request_payload: dict
    config_snapshot: dict
    stages: dict
    summary: dict
    warnings: dict
    error_message: str | None
    run_dir: str | None
    process_id: int | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobArtifactOut(BaseModel):
    key: str
    filename: str
    size_bytes: int
    updated_at: datetime


class ProviderModelOut(BaseModel):
    id: str
    label: str


class GeneratedBookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    title: str
    topic: str
    status: str
    run_dir: str
    latex_path: str | None
    pdf_path: str | None
    summary_metrics: dict
    artifact_paths: dict
    created_at: datetime
