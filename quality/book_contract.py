from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Domain = Literal[
    "technology",
    "software_engineering",
    "engineering",
    "psychology",
    "mental_health",
    "philosophy",
    "ethics",
    "history",
    "politics",
    "society",
    "business",
    "management",
    "marketing",
    "science",
    "math",
    "medicine_adjacent",
    "education",
    "self_help",
    "academic_explainer",
    "general_nonfiction",
]

BookType = Literal[
    "conceptual_guide",
    "textbook",
    "exam_prep",
    "practical_handbook",
    "implementation_guide",
    "implementation_manual",
    "manual",
    "project_based",
    "project_based_book",
    "research_survey",
    "academic_explainer",
    "argumentative",
    "reference",
]

AudienceLevel = Literal["beginner", "intermediate", "advanced", "mixed"]
EvidenceStandard = Literal["light", "standard", "research_grounded", "academic", "primary_source", "safety_sensitive"]
FreshnessRequirement = Literal["low", "medium", "high"]
RiskLevel = Literal["low", "medium", "high"]


class BookContractProfile(BaseModel):
    """Compatibility view for older pipeline code."""

    model_config = ConfigDict(extra="forbid")

    domain: str = "general_nonfiction"
    subdomain: str = ""
    book_type: str = "conceptual_guide"
    audience_level: str = "intermediate"
    required_evidence_level: str = "standard"
    implementation_heavy: bool = False
    code_validation_needed: bool = False
    formula_validation_needed: bool = False
    academic_source_grounding_needed: bool = False
    legal_medical_financial_caution_needed: bool = False
    freshness_current_research_important: bool = False


class BookContract(BaseModel):
    """Domain-aware generation contract shared by writing, QA, and repair."""

    model_config = ConfigDict(extra="forbid")

    domain: Domain = "general_nonfiction"
    subdomain: str = ""
    book_type: BookType = "conceptual_guide"
    audience_level: AudienceLevel = "intermediate"
    tone: str = "clear and supportive"
    pedagogy_style: str = "clear structured explanation"
    evidence_standard: EvidenceStandard = "standard"
    source_policy: str = "Ground important factual claims in relevant sources; do not invent sources, quotes, dates, statistics, or case studies."
    visual_policy: str = "Use visuals/tables only when they add structure, comparison, chronology, process, or decision value."
    risk_level: RiskLevel = "low"
    freshness_requirement: FreshnessRequirement = "medium"
    implementation_heavy: bool = False
    code_expected: bool = False
    formula_expected: bool = False
    project_based: bool = False
    research_heavy: bool = False
    sensitive_domain: bool = False
    must_not_do: list[str] = Field(default_factory=list)
    activated_validator_hints: list[str] = Field(default_factory=list)

    # Useful continuity fields retained for existing prompts/state.
    user_goal: str = ""
    thesis: str = ""
    central_promise: str = ""
    expected_depth: str = "intermediate"
    structure_pattern: str = "conceptual progression"
    examples_strategy: str = "Use concrete examples only where they clarify the section purpose."
    terminology_policy: str = "Define important terms once and reuse them consistently."
    citation_policy: str = "Use citations only where they support the claim being made."
    diagram_table_policy: str = "Use visuals/tables only when they add reader value."
    domain_constraints: list[str] = Field(default_factory=list)
    activated_validators: list[str] = Field(default_factory=list)
    validator_rationales: dict[str, str] = Field(default_factory=dict)

    @property
    def profile(self) -> BookContractProfile:
        return BookContractProfile(
            domain=self.domain,
            subdomain=self.subdomain,
            book_type=self.book_type,
            audience_level=self.audience_level,
            required_evidence_level=self.evidence_standard,
            implementation_heavy=self.implementation_heavy,
            code_validation_needed=self.code_expected,
            formula_validation_needed=self.formula_expected,
            academic_source_grounding_needed=self.research_heavy,
            legal_medical_financial_caution_needed=self.sensitive_domain,
            freshness_current_research_important=self.freshness_requirement == "high",
        )

    def compact_context(self) -> str:
        parts = [
            f"Domain: {self.domain}" + (f" / {self.subdomain}" if self.subdomain else ""),
            f"Book type: {self.book_type}",
            f"Audience: {self.audience_level}; depth: {self.expected_depth}",
            f"Tone: {self.tone}; pedagogy: {self.pedagogy_style}",
            f"Evidence: {self.evidence_standard}; freshness: {self.freshness_requirement}; risk: {self.risk_level}",
            f"Source policy: {self.source_policy}",
            f"Visual policy: {self.visual_policy}",
        ]
        if self.central_promise or self.thesis:
            parts.append(f"Central promise: {self.central_promise or self.thesis}")
        if self.must_not_do:
            parts.append("Must not do: " + "; ".join(self.must_not_do[:12]))
        if self.activated_validator_hints:
            parts.append("Validator hints: " + ", ".join(self.activated_validator_hints))
        return "\n".join(parts)


DOMAIN_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("psychology", ("psychology", "mental health", "therapy", "trauma", "diagnosis", "behavior", "cognitive", "emotion", "habit")),
    ("philosophy", ("philosophy", "ethics", "epistemology", "metaphysics", "argument", "stoicism", "kant", "aristotle")),
    ("history", ("history", "historical", "chronology", "revolution", "empire", "war", "ancient", "medieval")),
    ("politics", ("politics", "policy", "government", "election", "democracy", "state power")),
    ("business", ("business", "management", "strategy", "leadership", "startup", "marketing", "sales", "operations")),
    ("science", ("science", "physics", "chemistry", "biology", "climate", "neuroscience", "experiment")),
    ("math", ("math", "mathematics", "statistics", "probability", "algebra", "calculus", "proof", "formula")),
    ("medicine_adjacent", ("medicine", "medical", "clinical", "health", "nutrition", "sleep", "wellness")),
    ("education", ("education", "teaching", "curriculum", "textbook", "exam prep", "students", "classroom")),
    ("software_engineering", ("software", "programming", "code", "api", "devops", "database", "python", "javascript", "typescript")),
    ("technology", ("technology", "cloud", "platform", "cybersecurity", "infrastructure", "kubernetes")),
    ("engineering", ("engineering", "systems engineering", "mechanical", "electrical", "civil")),
    ("self_help", ("self-help", "personal development", "productivity", "mindset", "confidence")),
    ("academic_explainer", ("academic explainer", "literature review", "research survey", "scholarly")),
)


def classify_book_contract(
    user_input: dict[str, Any],
    outline: Optional[dict[str, Any]] = None,
    research_summary: Optional[dict[str, Any]] = None,
) -> BookContract:
    outline = _model_to_dict(outline) if outline is not None else None
    research_summary = _model_to_dict(research_summary) if research_summary is not None else None
    text = _joined_text(user_input, outline, research_summary)
    domain = _detect_domain(text)
    book_type = _detect_book_type(text, user_input)
    audience_level = _detect_audience(text)
    tone = str(user_input.get("tone") or "clear and supportive")
    pedagogy_style = _detect_pedagogy(text, book_type, domain)

    code_expected = _has_any(text, ("code", "programming", "api", "devops", "software", "python", "javascript", "typescript", "cli", "command", "configuration"))
    implementation_heavy = book_type in {"implementation_guide", "implementation_manual", "manual", "project_based", "project_based_book"} or _has_any(
        text, ("implementation guide", "technical manual", "software walkthrough", "devops walkthrough", "procedure manual", "step-by-step implementation")
    ) or (code_expected and _has_any(text, ("hands-on", "walkthrough", "build", "implementation", "project")))
    formula_expected = domain in {"math", "science"} or _has_any(text, ("math", "statistics", "physics", "chemistry", "proof", "formula", "equation", "calculation"))
    project_based = book_type in {"project_based", "project_based_book"} or bool(user_input.get("project_based")) or _has_any(text, ("project-based", "running project", "one project"))
    sensitive_domain = domain in {"psychology", "medicine_adjacent"} or _has_any(
        text, ("mental health", "therapy", "trauma", "diagnosis", "medicine", "medical", "law", "legal", "finance", "financial", "investment")
    )
    research_heavy = _detect_research_heavy(text, user_input, research_summary, domain, book_type)
    risk_level = _risk_level(domain, sensitive_domain)
    freshness_requirement = _freshness(text, domain, research_heavy)
    evidence_standard = _evidence_standard(domain, book_type, research_heavy, sensitive_domain)
    subdomain = _subdomain(text, domain)
    must_not_do = _must_not_do(domain, code_expected, sensitive_domain)
    activated_validator_hints = _validator_hints(
        domain=domain,
        book_type=book_type,
        implementation_heavy=implementation_heavy,
        code_expected=code_expected,
        formula_expected=formula_expected,
        project_based=project_based,
        sensitive_domain=sensitive_domain,
    )
    goal = _goal_text(user_input)
    topic = str(user_input.get("topic") or user_input.get("title") or "the requested book").strip()

    return BookContract(
        domain=domain,  # type: ignore[arg-type]
        subdomain=subdomain,
        book_type=book_type,  # type: ignore[arg-type]
        audience_level=audience_level,  # type: ignore[arg-type]
        tone=tone,
        pedagogy_style=pedagogy_style,
        evidence_standard=evidence_standard,  # type: ignore[arg-type]
        source_policy=_source_policy(evidence_standard, domain),
        visual_policy=_visual_policy(domain, book_type),
        risk_level=risk_level,  # type: ignore[arg-type]
        freshness_requirement=freshness_requirement,  # type: ignore[arg-type]
        implementation_heavy=implementation_heavy,
        code_expected=code_expected,
        formula_expected=formula_expected,
        project_based=project_based,
        research_heavy=research_heavy,
        sensitive_domain=sensitive_domain,
        must_not_do=must_not_do,
        activated_validator_hints=activated_validator_hints,
        user_goal=goal,
        thesis=f"{topic} for {user_input.get('audience') or 'the intended reader'}",
        central_promise=goal or f"Help the reader understand and apply {topic} at the requested depth.",
        expected_depth=str(user_input.get("depth") or audience_level),
        structure_pattern=_structure_pattern(domain, book_type),
        examples_strategy=_examples_strategy(domain, book_type),
        domain_constraints=must_not_do,
    )


class BookContractClassifier:
    def classify(self, planner_input: dict[str, Any], book_plan: Any = None) -> BookContract:
        outline = _model_to_dict(book_plan)
        return classify_book_contract(planner_input, outline=outline)

    def classify_profile(self, planner_input: dict[str, Any], book_plan: Any = None) -> BookContractProfile:
        return self.classify(planner_input, book_plan).profile


def _model_to_dict(value: Any) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return None


def _joined_text(*objects: Any) -> str:
    chunks: list[str] = []

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, (list, tuple, set)):
            for nested in value:
                visit(nested)
        else:
            chunks.append(str(value))

    for obj in objects:
        visit(obj)
    return " ".join(chunks).casefold()


import re

def _has_any(text: str, signals: tuple[str, ...]) -> bool:
    for signal in signals:
        if re.search(r"\b" + re.escape(signal) + r"\b", text, re.I):
            return True
    return False


def _detect_domain(text: str) -> str:
    best_domain = "general_nonfiction"
    best_score = 0
    for domain, signals in DOMAIN_SIGNALS:
        score = sum(1 for signal in signals if signal in text)
        if score > best_score:
            best_domain = domain
            best_score = score
    if best_domain == "medicine_adjacent" and "psychology" in text:
        return "psychology"
    return best_domain


def _detect_book_type(text: str, user_input: dict[str, Any]) -> str:
    explicit = str(user_input.get("book_type") or "").casefold().replace("_", " ")
    if "project" in explicit or _has_any(text, ("project-based", "running project", "one project")):
        return "project_based_book"
    if "implementation" in explicit:
        return "implementation_guide"
    if "manual" in explicit:
        return "manual"
    if "exam" in explicit or _has_any(text, ("exam prep", "certification", "practice test")):
        return "exam_prep"
    if "textbook" in explicit or "textbook" in text:
        return "textbook"
    if "research" in explicit or _has_any(text, ("research survey", "literature review", "state of the art")):
        return "research_survey"
    if "academic" in explicit or "academic explainer" in text:
        return "academic_explainer"
    if _has_any(text, ("handbook", "playbook", "practical guide")):
        return "practical_handbook"
    if _has_any(text, ("argument", "argumentative", "essay")):
        return "argumentative"
    if "reference" in explicit:
        return "reference"
    return "conceptual_guide"


def _detect_audience(text: str) -> str:
    if _has_any(text, ("advanced", "researcher", "researchers", "expert", "experts", "professional", "professionals", "graduate")):
        return "advanced"
    if _has_any(text, ("beginner", "zero knowledge", "kids", "simple", "novice", "introductory", "new to")):
        return "beginner"
    if _has_any(text, ("beginner to intermediate", "mixed audience", "broad audience")):
        return "mixed"
    return "intermediate"


def _detect_pedagogy(text: str, book_type: str, domain: str) -> str:
    if book_type in {"project_based", "project_based_book"}:
        return "cumulative project-based learning"
    if book_type in {"textbook", "exam_prep"}:
        return "scaffolded objectives, definitions, worked examples, and checks for understanding"
    if book_type in {"manual", "implementation_guide", "implementation_manual", "practical_handbook"}:
        return "actionable workflow with examples, cautions, and decision points"
    if domain == "philosophy":
        return "argument-first exposition with definitions, objections, and responses"
    if domain in {"history", "politics", "society"}:
        return "chronological and source-aware explanation"
    if domain == "psychology":
        return "careful research-grounded explanation with practical but cautious framing"
    return "clear structured explanation"


def _detect_research_heavy(text: str, user_input: dict[str, Any], research_summary: Optional[dict[str, Any]], domain: str, book_type: str) -> bool:
    source_usage = str(user_input.get("source_usage") or "").casefold()
    if source_usage in {"research-heavy", "research_heavy", "academic", "scientific", "current", "latest"}:
        return True
    if _has_any(text, ("research-heavy", "academic", "scientific", "current research", "latest", "evidence-based", "literature review")):
        return True
    if research_summary:
        return True
    return domain in {"psychology", "science", "medicine_adjacent", "academic_explainer"} or book_type in {"research_survey", "academic_explainer"}


def _risk_level(domain: str, sensitive: bool) -> str:
    if sensitive:
        return "high" if domain in {"psychology", "medicine_adjacent"} else "medium"
    if domain in {"business", "science", "self_help"}:
        return "medium"
    return "low"


def _freshness(text: str, domain: str, research_heavy: bool) -> str:
    if _has_any(text, ("latest", "current", "recent", "202", "frontier", "state of the art")):
        return "high"
    if domain in {"technology", "software_engineering", "science", "medicine_adjacent", "psychology"}:
        return "high" if research_heavy else "medium"
    if domain in {"history", "philosophy", "math"}:
        return "low"
    return "medium"


def _evidence_standard(domain: str, book_type: str, research_heavy: bool, sensitive: bool) -> str:
    if sensitive:
        return "safety_sensitive"
    if domain == "history":
        return "primary_source"
    if domain == "philosophy":
        return "academic"
    if research_heavy or book_type in {"research_survey", "academic_explainer"}:
        return "research_grounded"
    return "standard"


def _subdomain(text: str, domain: str) -> str:
    candidates = {
        "psychology": ("clinical psychology", "cognitive psychology", "social psychology", "behavior change", "habits"),
        "philosophy": ("ethics", "epistemology", "metaphysics", "logic", "political philosophy"),
        "history": ("ancient history", "modern history", "military history", "intellectual history"),
        "business": ("strategy", "leadership", "marketing", "operations", "management"),
        "software_engineering": ("api", "backend", "frontend", "devops", "databases", "testing"),
        "science": ("physics", "chemistry", "biology", "climate", "neuroscience"),
    }
    for candidate in candidates.get(domain, ()):
        if candidate in text:
            return candidate
    return ""


def _goal_text(user_input: dict[str, Any]) -> str:
    goals = user_input.get("goals") or user_input.get("goal") or []
    if isinstance(goals, str):
        return goals.strip()
    if isinstance(goals, list):
        return "; ".join(str(goal).strip() for goal in goals if str(goal).strip())
    return ""


def _source_policy(evidence_standard: str, domain: str) -> str:
    if evidence_standard == "safety_sensitive":
        return "Use credible, current, high-authority sources; separate evidence from advice; avoid personalized diagnosis, treatment, legal, or financial guidance."
    if domain == "history":
        return "Ground dates, events, actors, and quotations in sources; distinguish primary sources, secondary scholarship, and interpretation."
    if domain == "philosophy":
        return "Attribute arguments and interpretations; never invent quotations or assign positions without support."
    if evidence_standard in {"research_grounded", "academic", "primary_source"}:
        return "Use credible sources for important claims; preserve uncertainty and conflicting viewpoints."
    return "Use relevant sources for factual claims; do not invent citations or unsupported specifics."


def _visual_policy(domain: str, book_type: str) -> str:
    if domain == "history":
        return "Prefer timelines, maps, chronology tables, and cause/consequence diagrams when useful."
    if domain == "philosophy":
        return "Prefer argument maps, term maps, and comparison matrices when useful."
    if book_type in {"manual", "practical_handbook", "implementation_guide", "implementation_manual"}:
        return "Prefer process flows, decision trees, checklists, and procedure tables when they add value."
    if book_type in {"textbook", "exam_prep"}:
        return "Prefer learning roadmaps, worked-example tables, concept maps, and practice matrices."
    return "Use visuals/tables only when they clarify structure or comparison."


def _structure_pattern(domain: str, book_type: str) -> str:
    if book_type in {"project_based", "project_based_book"}:
        return "one cumulative project/scenario progression"
    if book_type in {"textbook", "exam_prep"}:
        return "learning objective -> concept -> worked example -> practice -> rationale"
    if book_type in {"manual", "implementation_guide", "implementation_manual", "practical_handbook"}:
        return "situation -> action -> caution -> decision point -> check"
    if domain == "history":
        return "chronology -> context -> evidence -> interpretation -> consequences"
    if domain == "philosophy":
        return "thesis -> definitions -> argument -> objection -> response"
    return "context -> explanation -> example -> caveat -> takeaway"


def _examples_strategy(domain: str, book_type: str) -> str:
    if book_type in {"project_based", "project_based_book"}:
        return "Maintain one running project or scenario and advance it cumulatively."
    if domain == "business":
        return "Use realistic examples; mark fictional examples clearly; do not invent real case studies."
    if domain == "history":
        return "Use sourced events, actors, dates, and disputed interpretations; do not invent anecdotes."
    if domain == "philosophy":
        return "Use thought experiments, attributed interpretations, objections, and argument maps."
    return "Use concrete examples that advance understanding and match the audience level."


def _must_not_do(domain: str, code_expected: bool, sensitive: bool) -> list[str]:
    rules = [
        "Do not leak internal QA notes, TODOs, placeholders, or validation warnings into the final manuscript.",
        "Do not invent sources, quotes, dates, statistics, APIs, commands, studies, or real case studies.",
        "Do not drift away from the requested domain, audience, book type, or pedagogy.",
    ]
    if domain == "psychology":
        rules.extend([
            "Do not diagnose.",
            "Avoid diagnosis-style language unless explicitly framed as informational.",
            "Do not overclaim causality.",
            "Distinguish research-backed claims from advice.",
            "Use cautious language for mental health.",
        ])
    if domain == "philosophy":
        rules.extend([
            "Do not invent quotes.",
            "Do not attribute claims without source.",
            "Preserve argument structure.",
            "Distinguish interpretation from established position.",
        ])
    if domain in {"history", "politics", "society"}:
        rules.extend([
            "Do not invent dates/events.",
            "Preserve chronology.",
            "Distinguish fact from interpretation.",
            "Mark disputed claims.",
        ])
    if domain in {"technology", "software_engineering", "engineering"} or code_expected:
        rules.extend([
            "Do not present broken runnable code.",
            "Do not invent APIs or commands.",
            "Mark pseudocode clearly.",
        ])
    if domain in {"business", "management", "marketing"}:
        rules.extend([
            "Do not invent real case studies.",
            "Mark fictional examples clearly.",
            "Keep recommendations actionable.",
        ])
    if sensitive:
        rules.append("Do not provide personalized medical, legal, financial, diagnostic, or treatment advice.")
    if not code_expected:
        rules.append("Do not force code-oriented validators or programming examples into non-technical content.")
    return rules


def _validator_hints(
    *,
    domain: str,
    book_type: str,
    implementation_heavy: bool,
    code_expected: bool,
    formula_expected: bool,
    project_based: bool,
    sensitive_domain: bool,
) -> list[str]:
    hints = ["source_grounding", "claim_evidence", "continuity", "placeholder_detection"]
    if code_expected or implementation_heavy:
        hints.append("code_validator")
    if formula_expected:
        hints.append("formula_validator")
    if domain in {"history", "politics", "society"}:
        hints.append("chronology_validator")
    if domain in {"philosophy", "ethics"} or book_type == "argumentative":
        hints.append("argument_validator")
    if domain in {"psychology", "science", "education", "self_help"}:
        hints.append("research_method_caution_validator")
    if sensitive_domain:
        hints.append("safety_language_validator")
    if book_type in {"manual", "practical_handbook", "implementation_guide"} or implementation_heavy:
        hints.append("procedure_validator")
    if book_type in {"textbook", "exam_prep"}:
        hints.append("exercise_validator")
    if project_based:
        hints.append("project_continuity_validator")
    if domain in {"business", "management", "marketing"}:
        hints.append("case_study_validator")
    return hints
