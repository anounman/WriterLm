from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Domain = Literal[
    "technology",
    "software_engineering",
    "machine_learning",
    "psychology",
    "philosophy",
    "business",
    "history",
    "education",
    "self_help",
    "science",
    "health_adjacent",
    "academic_explainer",
    "math",
    "general_nonfiction",
]

BookKind = Literal[
    "conceptual_guide",
    "textbook",
    "practical_handbook",
    "implementation_manual",
    "project_based_book",
    "exam_prep",
    "research_survey",
    "academic_explainer",
    "essay_argument",
    "reference_handbook",
]

AudienceLevel = Literal["beginner", "intermediate", "advanced", "mixed"]
EvidenceStandard = Literal["light", "standard", "research_grounded", "academic", "primary_source", "safety_sensitive"]
FreshnessRequirement = Literal["low", "medium", "high"]
RiskLevel = Literal["low", "medium", "high"]


class BookContractProfile(BaseModel):
    """Compact classifier output consumed by downstream stages."""

    model_config = ConfigDict(extra="forbid")

    domain: Domain = "general_nonfiction"
    subdomain: str = ""
    book_type: BookKind = "conceptual_guide"
    audience_level: AudienceLevel = "intermediate"
    required_evidence_level: EvidenceStandard = "standard"
    implementation_heavy: bool = False
    code_validation_needed: bool = False
    formula_validation_needed: bool = False
    academic_source_grounding_needed: bool = False
    legal_medical_financial_caution_needed: bool = False
    freshness_current_research_important: bool = False


class BookContract(BaseModel):
    """Persistent promise that keeps research, writing, validation, and repair aligned."""

    model_config = ConfigDict(extra="forbid")

    profile: BookContractProfile = Field(default_factory=BookContractProfile)
    domain: Domain = "general_nonfiction"
    subdomain: str = ""
    book_type: BookKind = "conceptual_guide"
    audience_level: AudienceLevel = "intermediate"
    user_goal: str = ""
    thesis: str = ""
    central_promise: str = ""
    pedagogy_style: str = "clear structured explanation"
    tone: str = "clear and supportive"
    expected_depth: str = "intermediate"
    source_requirements: list[str] = Field(default_factory=list)
    evidence_standard: EvidenceStandard = "standard"
    structure_pattern: str = "conceptual progression"
    examples_strategy: str = "use concrete examples only where they clarify the section purpose"
    terminology_policy: str = "define important terms once and reuse them consistently"
    citation_policy: str = "cite or link only sources that actually support the claims used"
    diagram_table_policy: str = "include visuals only when they add structure, comparison, process, chronology, or decision value"
    risk_level: RiskLevel = "low"
    freshness_requirement: FreshnessRequirement = "medium"
    must_not_do: list[str] = Field(default_factory=list)
    activated_validators: list[str] = Field(default_factory=list)
    validator_rationales: dict[str, str] = Field(default_factory=dict)
    domain_constraints: list[str] = Field(default_factory=list)

    def compact_context(self) -> str:
        parts = [
            f"Domain: {self.domain}" + (f" / {self.subdomain}" if self.subdomain else ""),
            f"Book type: {self.book_type}",
            f"Audience: {self.audience_level}; depth: {self.expected_depth}",
            f"Central promise: {self.central_promise or self.thesis}",
            f"Pedagogy: {self.pedagogy_style}",
            f"Evidence standard: {self.evidence_standard}; freshness: {self.freshness_requirement}; risk: {self.risk_level}",
            f"Examples strategy: {self.examples_strategy}",
            f"Terminology policy: {self.terminology_policy}",
            f"Citation policy: {self.citation_policy}",
            f"Visual/table policy: {self.diagram_table_policy}",
        ]
        if self.domain_constraints:
            parts.append("Domain constraints: " + "; ".join(self.domain_constraints[:8]))
        if self.must_not_do:
            parts.append("Must not do: " + "; ".join(self.must_not_do[:10]))
        if self.activated_validators:
            parts.append("Active validators: " + ", ".join(self.activated_validators))
        return "\n".join(parts)


class TaxonomyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: Domain
    signals: tuple[str, ...]
    evidence_standard: EvidenceStandard = "standard"
    freshness: FreshnessRequirement = "medium"
    risk: RiskLevel = "low"
    constraints: tuple[str, ...] = ()


DOMAIN_TAXONOMY: tuple[TaxonomyProfile, ...] = (
    TaxonomyProfile(domain="machine_learning", signals=("machine learning", "ml", "neural", "llm", "rag", "model training"), evidence_standard="research_grounded", freshness="high", constraints=("validate formulas, metrics, datasets, and claims about model behavior when present",)),
    TaxonomyProfile(domain="software_engineering", signals=("software", "programming", "code", "api", "python", "javascript", "typescript", "database", "devops", "architecture"), evidence_standard="standard", freshness="high", constraints=("validate runnable code, commands, configuration, APIs, and procedures only when the book includes them",)),
    TaxonomyProfile(domain="technology", signals=("cloud", "aws", "kubernetes", "platform", "cybersecurity", "networking", "infrastructure"), evidence_standard="standard", freshness="high", constraints=("verify product, command, API, configuration, and procedure claims when included",)),
    TaxonomyProfile(domain="psychology", signals=("psychology", "cognitive", "therapy", "mental health", "behavior", "emotion", "motivation", "habit"), evidence_standard="research_grounded", freshness="high", risk="high", constraints=("distinguish research-backed claims from advice", "avoid diagnosis or treatment language unless explicitly informational", "avoid overclaiming causality")),
    TaxonomyProfile(domain="health_adjacent", signals=("health", "wellness", "nutrition", "sleep", "stress", "medical", "clinical"), evidence_standard="safety_sensitive", freshness="high", risk="high", constraints=("use informational caution language", "avoid diagnosis, treatment, or personalized medical advice", "flag uncertain or contested claims")),
    TaxonomyProfile(domain="philosophy", signals=("philosophy", "ethics", "epistemology", "metaphysics", "stoicism", "kant", "aristotle", "argument"), evidence_standard="academic", freshness="low", constraints=("validate argument coherence", "define terms consistently", "separate interpretation from established scholarship", "do not invent quotations or attributions")),
    TaxonomyProfile(domain="history", signals=("history", "historical", "war", "empire", "revolution", "ancient", "medieval", "chronology"), evidence_standard="primary_source", freshness="low", constraints=("verify chronology, dates, actors, events, and source type", "handle disputed interpretations carefully", "do not invent events or quotes")),
    TaxonomyProfile(domain="business", signals=("business", "management", "strategy", "leadership", "startup", "marketing", "sales", "operations", "finance"), evidence_standard="standard", freshness="medium", risk="medium", constraints=("validate frameworks and examples", "avoid fake case studies unless clearly fictional", "connect recommendations to evidence or stated assumptions")),
    TaxonomyProfile(domain="education", signals=("education", "teaching", "learning", "curriculum", "pedagogy", "classroom", "exam prep"), evidence_standard="research_grounded", freshness="medium", constraints=("track learning objectives, prerequisites, examples, exercises, and scaffolding",)),
    TaxonomyProfile(domain="science", signals=("science", "physics", "biology", "chemistry", "climate", "astronomy", "neuroscience"), evidence_standard="research_grounded", freshness="high", constraints=("validate formulas, causal claims, uncertainty, and experimental evidence when present",)),
    TaxonomyProfile(domain="math", signals=("math", "mathematics", "algebra", "calculus", "proof", "theorem", "statistics", "probability"), evidence_standard="standard", freshness="low", constraints=("validate formulas, worked examples, definitions, and proof flow",)),
    TaxonomyProfile(domain="self_help", signals=("self-help", "personal development", "productivity", "mindset", "confidence", "habits"), evidence_standard="standard", freshness="medium", risk="medium", constraints=("distinguish evidence-backed practices from personal advice", "avoid universal promises")),
)


class BookContractClassifier:
    """Deterministic, extensible classifier; LLM layers can refine this later if desired."""

    def classify(self, planner_input: dict[str, Any], book_plan: Any | None = None) -> BookContract:
        text = _joined_text(planner_input, book_plan)
        profile = self.classify_profile(planner_input, book_plan)
        goal = _goal_text(planner_input)
        topic = str(planner_input.get("topic") or getattr(book_plan, "title", "") or "").strip()
        tone = str(planner_input.get("tone") or "clear and supportive")
        depth = str(planner_input.get("depth") or getattr(book_plan, "depth", "") or profile.audience_level)
        thesis = _infer_thesis(topic, planner_input, book_plan)
        contract = BookContract(
            profile=profile,
            domain=profile.domain,
            subdomain=profile.subdomain,
            book_type=profile.book_type,
            audience_level=profile.audience_level,
            user_goal=goal,
            thesis=thesis,
            central_promise=thesis,
            pedagogy_style=_infer_pedagogy(planner_input, profile),
            tone=tone,
            expected_depth=depth,
            source_requirements=_source_requirements(profile),
            evidence_standard=profile.required_evidence_level,
            structure_pattern=_structure_pattern(profile),
            examples_strategy=_examples_strategy(profile),
            risk_level=_risk_level(profile),
            freshness_requirement="high" if profile.freshness_current_research_important else _taxonomy_for(profile.domain).freshness if _taxonomy_for(profile.domain) else "medium",
            must_not_do=_must_not_do(profile),
            domain_constraints=list(_taxonomy_for(profile.domain).constraints if _taxonomy_for(profile.domain) else ()),
        )
        if "advanced" in text and contract.audience_level != "advanced":
            contract.must_not_do.append("Do not silently downgrade advanced material to intermediate coverage.")
        return contract

    def classify_profile(self, planner_input: dict[str, Any], book_plan: Any | None = None) -> BookContractProfile:
        text = _joined_text(planner_input, book_plan)
        taxonomy = _best_taxonomy(text)
        book_type = _infer_book_type(text, planner_input)
        audience_level = _infer_audience_level(text, planner_input, book_plan)
        implementation_heavy = book_type in {"implementation_manual", "project_based_book"} or _contains_any(text, ("implementation", "build", "hands-on", "walkthrough", "manual", "procedure"))
        software_like = taxonomy.domain in {"software_engineering", "machine_learning", "technology"} and _contains_any(text, ("code", "programming", "python", "javascript", "api", "cli", "command", "configuration", "build"))
        formula_needed = taxonomy.domain in {"math", "science", "machine_learning"} or _contains_any(text, ("formula", "equation", "proof", "theorem", "statistics", "calculation"))
        academic_needed = taxonomy.evidence_standard in {"research_grounded", "academic", "primary_source", "safety_sensitive"} or book_type in {"research_survey", "academic_explainer"}
        safety_needed = taxonomy.risk == "high" or _contains_any(text, ("legal", "medical", "financial", "health", "mental health", "therapy", "clinical", "investment"))
        freshness = taxonomy.freshness == "high" or _contains_any(text, ("latest", "current", "recent", "202", "frontier", "state of the art"))
        return BookContractProfile(
            domain=taxonomy.domain,
            subdomain=_infer_subdomain(text, taxonomy.domain),
            book_type=book_type,
            audience_level=audience_level,
            required_evidence_level="safety_sensitive" if safety_needed else "academic" if book_type in {"research_survey", "academic_explainer"} else taxonomy.evidence_standard,
            implementation_heavy=implementation_heavy,
            code_validation_needed=software_like,
            formula_validation_needed=formula_needed,
            academic_source_grounding_needed=academic_needed,
            legal_medical_financial_caution_needed=safety_needed,
            freshness_current_research_important=freshness,
        )


def classify_book_contract(planner_input: dict[str, Any], book_plan: Any | None = None) -> BookContract:
    return BookContractClassifier().classify(planner_input, book_plan)


def _joined_text(planner_input: dict[str, Any], book_plan: Any | None) -> str:
    fragments = [
        planner_input.get("topic"),
        planner_input.get("audience"),
        planner_input.get("tone"),
        planner_input.get("depth"),
        planner_input.get("book_type"),
        planner_input.get("theory_practice_balance"),
        planner_input.get("pedagogy_style"),
        planner_input.get("running_project_description"),
        " ".join(str(g) for g in planner_input.get("goals") or []),
    ]
    if book_plan is not None:
        fragments.extend([getattr(book_plan, "title", ""), getattr(book_plan, "audience", ""), getattr(book_plan, "depth", "")])
    return " ".join(str(item or "") for item in fragments).casefold()


def _contains_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def _best_taxonomy(text: str) -> TaxonomyProfile:
    best = (0, TaxonomyProfile(domain="general_nonfiction", signals=()))
    for profile in DOMAIN_TAXONOMY:
        score = sum(1 for signal in profile.signals if signal in text)
        if score > best[0]:
            best = (score, profile)
    return best[1]


def _taxonomy_for(domain: Domain) -> TaxonomyProfile | None:
    return next((item for item in DOMAIN_TAXONOMY if item.domain == domain), None)


def _infer_book_type(text: str, planner_input: dict[str, Any]) -> BookKind:
    explicit = str(planner_input.get("book_type") or "").casefold()
    mapped = {
        "textbook": "textbook",
        "practice_workbook": "exam_prep",
        "course_companion": "textbook",
        "implementation_guide": "implementation_manual",
        "reference_handbook": "reference_handbook",
        "conceptual_guide": "conceptual_guide",
        "exam_prep": "exam_prep",
    }
    if explicit in mapped:
        return mapped[explicit]  # type: ignore[return-value]
    if planner_input.get("project_based") or _contains_any(text, ("project-based", "running project", "build a project")):
        return "project_based_book"
    if _contains_any(text, ("exam", "certification", "practice test", "workbook")):
        return "exam_prep"
    if _contains_any(text, ("implementation manual", "manual", "handbook", "playbook", "practical")):
        return "practical_handbook"
    if _contains_any(text, ("research survey", "literature review", "state of the art", "academic")):
        return "research_survey"
    if _contains_any(text, ("argument", "essay", "thesis")):
        return "essay_argument"
    if _contains_any(text, ("course", "textbook", "curriculum", "beginner textbook")):
        return "textbook"
    return "conceptual_guide"


def _infer_audience_level(text: str, planner_input: dict[str, Any], book_plan: Any | None) -> AudienceLevel:
    depth = str(planner_input.get("depth") or getattr(book_plan, "depth", "") or "").casefold()
    if depth in {"introductory", "beginner"} or _contains_any(text, ("beginner", "novice", "introductory", "getting started")):
        return "beginner"
    if depth == "advanced" or _contains_any(text, ("advanced", "expert", "graduate")):
        return "advanced"
    if _contains_any(text, ("beginner to intermediate", "mixed", "broad audience")):
        return "mixed"
    return "intermediate"


def _infer_subdomain(text: str, domain: Domain) -> str:
    candidates = {
        "software_engineering": ("api design", "frontend", "backend", "distributed systems", "testing", "databases", "devops"),
        "machine_learning": ("llm", "rag", "deep learning", "computer vision", "nlp", "evaluation"),
        "psychology": ("cognitive psychology", "clinical psychology", "social psychology", "motivation", "habits"),
        "philosophy": ("ethics", "epistemology", "metaphysics", "political philosophy", "logic"),
        "history": ("ancient history", "modern history", "military history", "economic history", "intellectual history"),
        "business": ("strategy", "leadership", "operations", "marketing", "finance", "entrepreneurship"),
        "science": ("physics", "biology", "chemistry", "climate science", "neuroscience"),
    }
    for candidate in candidates.get(domain, ()):
        if candidate in text:
            return candidate
    return ""


def _goal_text(planner_input: dict[str, Any]) -> str:
    goals = planner_input.get("goals") or []
    if isinstance(goals, str):
        return goals
    return "; ".join(str(goal) for goal in goals if str(goal).strip())


def _infer_thesis(topic: str, planner_input: dict[str, Any], book_plan: Any | None) -> str:
    title = getattr(book_plan, "title", "") or topic
    audience = planner_input.get("audience") or getattr(book_plan, "audience", "") or "the intended reader"
    goals = _goal_text(planner_input)
    if goals:
        return f"{title} should help {audience} {goals}."
    return f"{title} should help {audience} understand and apply the subject at the requested depth."


def _infer_pedagogy(planner_input: dict[str, Any], profile: BookContractProfile) -> str:
    explicit = str(planner_input.get("pedagogy_style") or "").replace("_", " ").strip()
    if explicit and explicit != "auto":
        return explicit
    if profile.book_type == "project_based_book":
        return "cumulative project-based learning"
    if profile.book_type in {"exam_prep", "textbook"}:
        return "scaffolded objectives, definitions, worked examples, and checks for understanding"
    if profile.book_type in {"practical_handbook", "implementation_manual"}:
        return "actionable workflow, examples, cautions, and decision points"
    if profile.domain == "philosophy":
        return "argument-first exposition with careful terms and objections"
    if profile.domain == "history":
        return "chronological explanation with source-aware interpretation"
    return "clear structured explanation with concrete examples"


def _source_requirements(profile: BookContractProfile) -> list[str]:
    requirements = ["Use sources to ground important factual claims; do not invent citations, quotes, dates, statistics, or studies."]
    if profile.academic_source_grounding_needed:
        requirements.append("Prefer credible primary, academic, official, or high-authority sources appropriate to the domain.")
    if profile.freshness_current_research_important:
        requirements.append("Check freshness for current practices, recent research, product behavior, APIs, and guidance.")
    if profile.domain == "history":
        requirements.append("Distinguish primary sources, secondary scholarship, and disputed interpretations.")
    return requirements


def _structure_pattern(profile: BookContractProfile) -> str:
    if profile.book_type == "project_based_book":
        return "cumulative project/scenario progression"
    if profile.book_type in {"textbook", "exam_prep"}:
        return "learning objective -> concept -> worked example -> practice -> answer rationale"
    if profile.book_type == "implementation_manual":
        return "concept -> procedure -> validation -> troubleshooting -> integration"
    if profile.domain == "history":
        return "chronology -> context -> evidence -> interpretation -> consequences"
    if profile.domain == "philosophy":
        return "thesis -> definitions -> argument -> objection -> response"
    return "definition/context -> explanation -> example -> caveat -> reader takeaway"


def _examples_strategy(profile: BookContractProfile) -> str:
    if profile.book_type == "project_based_book":
        return "maintain one running project or scenario and advance it cumulatively"
    if profile.domain == "business":
        return "use realistic examples or clearly labeled fictional cases; avoid fake real-world case studies"
    if profile.domain == "history":
        return "use dated events, actors, and source-aware episodes; do not invent anecdotes"
    if profile.domain == "philosophy":
        return "use thought experiments, argument maps, and attributed interpretations"
    if profile.code_validation_needed:
        return "include runnable code or commands only when implementation is promised or necessary"
    return "use concrete examples, analogies, cases, or worked problems only when they advance understanding"


def _risk_level(profile: BookContractProfile) -> RiskLevel:
    if profile.legal_medical_financial_caution_needed or profile.required_evidence_level == "safety_sensitive":
        return "high"
    if profile.domain in {"business", "self_help", "science", "psychology"}:
        return "medium"
    return "low"


def _must_not_do(profile: BookContractProfile) -> list[str]:
    items = [
        "Do not drift into a different domain, book type, audience level, or pedagogy style.",
        "Do not leak internal QA notes, TODOs, placeholders, or validation warnings into the final manuscript.",
        "Do not include generic filler diagrams or tables that repeat prose without adding value.",
        "Do not invent sources, quotes, dates, statistics, case studies, or procedures.",
    ]
    if not profile.code_validation_needed:
        items.append("Do not force code-oriented validation language or programming examples into non-technical sections.")
    if profile.legal_medical_financial_caution_needed:
        items.append("Do not provide personalized medical, legal, financial, diagnostic, or treatment advice.")
    return items
