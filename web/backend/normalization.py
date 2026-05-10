"""Deterministic normalization layer for BookRequest payloads.

Runs AFTER the LLM parser and BEFORE the planner input is constructed.
Enforces domain-specific rules that are too unreliable for LLM parsing alone.

This module is pure-function, idempotent, and makes zero LLM calls.
"""

from __future__ import annotations

import re
from typing import Any


# ── Pattern libraries ────────────────────────────────────────────────────────

_URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+")

_NO_CODE_PHRASES = re.compile(
    r"\b(?:no\s+code|without\s+code|no\s+programming|avoid\s+programming)\b",
    re.IGNORECASE,
)

_CODE_HEAVY_PHRASES = re.compile(
    r"\b(?:code[\s-]*heavy|runnable\s+code|implementation[\s-]*heavy|"
    r"build\s+from\s+scratch|from\s+scratch\s+implementation)\b",
    re.IGNORECASE,
)

_SHOWCASE_PHRASES = re.compile(
    r"\b(?:showcase|homepage|demo|portfolio|polished|publication[\s-]*ready)\b",
    re.IGNORECASE,
)

_IMPLEMENTATION_PHRASES = re.compile(
    r"\b(?:build|implement|project[\s-]*based|hands[\s-]*on|"
    r"step[\s-]*by[\s-]*step\s+(?:guide|tutorial)|practical\s+guide|"
    r"implementation\s+guide|coding\s+project|develop\s+a|create\s+a)\b",
    re.IGNORECASE,
)

_PHILOSOPHY_KEYWORDS = re.compile(
    r"\b(?:philosophy|philosophical|ethics|ethical|moral\s+responsibility|"
    r"epistemology|ontology|metaphysics|free\s+will|existential|"
    r"determinism|phenomenology|hermeneutics|deontolog|utilitarianism|"
    r"virtue\s+ethics)\b",
    re.IGNORECASE,
)

_HISTORY_KEYWORDS = re.compile(
    r"\b(?:history|historical|chronolog|revolution|war|empire|"
    r"timeline|ancient|medieval|colonial|dynasty|"
    r"century|era|epoch|civilization)\b",
    re.IGNORECASE,
)

_PSYCHOLOGY_KEYWORDS = re.compile(
    r"\b(?:psychology|psychological|habit|focus|deep\s+work|productivity|"
    r"therapy|therapeutic|cognitive\s+behavioral|mental\s+health|"
    r"self[\s-]*help|well[\s-]*being|mindfulness|emotional\s+intelligence|"
    r"resilience|anxiety|depression|stress\s+management|counseling|counselling)\b",
    re.IGNORECASE,
)

_EVIDENCE_BASED_PHRASES = re.compile(
    r"\b(?:evidence[\s-]*based|research[\s-]*grounded|research[\s-]*backed|"
    r"scientifically[\s-]*supported)\b",
    re.IGNORECASE,
)

_BUSINESS_KEYWORDS = re.compile(
    r"\b(?:startup|founder|go[\s-]*to[\s-]*market|business|marketing|"
    r"positioning|strategy|product\s+strategy|entrepreneurship|"
    r"venture|growth|revenue|customer|branding)\b",
    re.IGNORECASE,
)

_MATH_KEYWORDS = re.compile(
    r"\b(?:mathematics|mathematical|algebra|calculus|linear\s+algebra|"
    r"differential\s+equations|topology|number\s+theory|statistics|"
    r"probability|theorem|proof|lemma|corollary|equation|formula|"
    r"physics|quantum|mechanics|electrodynamics|thermodynamics)\b",
    re.IGNORECASE,
)

_DIAGRAM_HEAVY_PHRASES = re.compile(
    r"\b(?:diagram[\s-]*heavy|visual|architecture|concept\s+maps|"
    r"flowcharts|diagrams)\b",
    re.IGNORECASE,
)

_BEGINNER_KEYWORDS = re.compile(
    r"\b(?:beginner|beginners|novice|newcomer|introduction|introductory|"
    r"getting\s+started|first[\s-]*time|basics|fundamentals|"
    r"zero\s+knowledge|simple)\b",
    re.IGNORECASE,
)

_ADVANCED_KEYWORDS = re.compile(
    r"\b(?:advanced|expert|senior|experienced|specialist|researcher|"
    r"graduate[\s-]*level|phd|doctoral|postgraduate|deep\s+dive|"
    r"professional)\b",
    re.IGNORECASE,
)

# Non-technical book domains where code defaults to "none"
_NON_TECHNICAL_DOMAINS = {
    "productivity", "psychology", "self-help", "self_help", "philosophy",
    "history", "business", "education", "general_nonfiction", "general",
    "society", "politics", "medicine_adjacent", "ethics",
}

# Technologies to extract from prompts
_STACK_TECHNOLOGIES = [
    "FastAPI", "Django", "Flask", "React", "Next.js",
    "PostgreSQL", "SQLite", "MySQL", "Redis",
    "Docker", "Docker Compose", "Kubernetes",
    "AWS", "Azure", "GCP", "Terraform",
    "Python", "JavaScript", "TypeScript",
    "SQLAlchemy", "Alembic", "pytest",
    "LangChain", "Chroma", "pgvector", "Pinecone", "FAISS",
]

# Compiled regex patterns for each technology, matching case-insensitively
# but preserving the canonical capitalization.
_STACK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (tech, re.compile(r"\b" + re.escape(tech) + r"\b", re.IGNORECASE))
    for tech in _STACK_TECHNOLOGIES
]


def _is_technical_context(parsed: dict[str, Any], text_pool: str) -> bool:
    """Return True if the request is about a technical/programming topic."""
    technical_signals = (
        "programming", "software", "api", "rest api", "devops", "infrastructure",
        "backend", "frontend", "full-stack", "microservice", "database", "cli",
        "code", "coding", "python", "javascript", "typescript", "docker",
        "kubernetes", "terraform", "deploy", "authentication", "authorization",
    )
    book_type = str(parsed.get("book_type") or "")
    if book_type in ("implementation_guide",):
        return True
    for signal in technical_signals:
        if re.search(r"\b" + re.escape(signal) + r"\b", text_pool, re.IGNORECASE):
            return True
    return False


def _is_nontechnical_domain(parsed: dict[str, Any], text_pool: str) -> bool:
    """Return True if the request is clearly non-technical."""
    topic = str(parsed.get("topic") or "").lower()
    for domain_key in _NON_TECHNICAL_DOMAINS:
        if domain_key.replace("_", " ") in topic or domain_key.replace("_", "-") in topic:
            return True
    # Check for domain-specific keywords
    for pattern in (_PHILOSOPHY_KEYWORDS, _HISTORY_KEYWORDS, _PSYCHOLOGY_KEYWORDS, _BUSINESS_KEYWORDS):
        if pattern.search(text_pool) and not _is_technical_context(parsed, text_pool):
            return True
    return False


def _add_unique(target: list[str], items: list[str]) -> list[str]:
    """Append items to target without duplicates, preserving order."""
    existing = {item.lower() for item in target}
    for item in items:
        if item.lower() not in existing:
            target.append(item)
            existing.add(item.lower())
    return target


# ── Main normalization function ──────────────────────────────────────────────

def normalize_book_request(parsed: dict[str, Any], original_prompt: str = "") -> dict[str, Any]:
    """Apply deterministic normalization rules to a parsed book request.

    Args:
        parsed: The merged BookRequest dict (may include generation_contract).
        original_prompt: The raw user prompt text for signal extraction.

    Returns:
        The normalized dict with a guaranteed ``generation_contract`` sub-dict.
        The function is **idempotent** — calling it twice yields the same result.
    """
    result = dict(parsed)
    contract = dict(result.get("generation_contract") or {})
    topic = str(result.get("topic") or "")
    audience = str(result.get("audience") or "")
    goals = result.get("goals") or []
    goals_text = " ".join(str(g) for g in goals)
    text_pool = f"{topic} {audience} {goals_text} {original_prompt}"

    is_technical = _is_technical_context(result, text_pool)
    is_nontechnical = _is_nontechnical_domain(result, text_pool)

    # ── Rule 1: URL extraction ───────────────────────────────────────────
    if original_prompt:
        urls_in_prompt = _URL_PATTERN.findall(original_prompt)
        clean_urls: list[str] = []
        seen: set[str] = set()
        for url in urls_in_prompt:
            url = url.rstrip(".,;:!?)")
            if url not in seen:
                clean_urls.append(url)
                seen.add(url)
        result["urls"] = clean_urls

    # ── Rule 2: No-code enforcement ──────────────────────────────────────
    explicit_no_code = _NO_CODE_PHRASES.search(text_pool)
    if explicit_no_code or result.get("code_density") == "none":
        contract.setdefault("code_artifact_policy", "no_code")
        if explicit_no_code:
            result["code_density"] = "none"
            _add_unique(
                contract.setdefault("forbidden_content", []),
                ["code examples", "programming filler", "terminal commands"],
            )

    # ── Rule 3: Code-heavy detection ─────────────────────────────────────
    if _CODE_HEAVY_PHRASES.search(text_pool) and is_technical:
        result["code_density"] = "high"
        contract.setdefault("implementation_style", "file_by_file")
        contract.setdefault("section_style", "file_by_file_implementation")
        contract.setdefault("code_artifact_policy", "file_labeled_code_required")

    # ── Rule 4: Showcase detection ───────────────────────────────────────
    if _SHOWCASE_PHRASES.search(text_pool):
        contract["showcase_candidate"] = True
        current_score = result.get("target_quality_score", 0) or 0
        if current_score < 80:
            result["target_quality_score"] = 80
        result["auto_repair"] = True
        result["sample_first"] = True
        if result.get("quality_mode") in (None, "fast_draft", "full_generation"):
            result["quality_mode"] = "full_auto_repair"
        _add_unique(
            contract.setdefault("success_criteria", []),
            [
                "homepage showcase-ready",
                "polished final manuscript",
                "coherent book arc",
                "no generic filler",
            ],
        )

    # ── Rule 5: Required stack extraction ────────────────────────────────
    if original_prompt:
        existing_stack = set(s.lower() for s in (contract.get("required_stack") or []))
        stack: list[str] = list(contract.get("required_stack") or [])
        for canonical, pattern in _STACK_PATTERNS:
            if pattern.search(original_prompt) and canonical.lower() not in existing_stack:
                stack.append(canonical)
                existing_stack.add(canonical.lower())
        if stack:
            contract["required_stack"] = stack

    # ── Rule 6: Technical implementation guide ───────────────────────────
    if (
        result.get("book_type") == "implementation_guide"
        or (result.get("project_based") and _IMPLEMENTATION_PHRASES.search(text_pool))
    ) and is_technical:
        # Only set code policy if no_code was NOT explicitly requested
        if contract.get("code_artifact_policy") != "no_code":
            if result.get("code_density") != "none":
                contract.setdefault("code_artifact_policy", "file_labeled_code_required")
            contract.setdefault("implementation_style", "file_by_file")
            contract.setdefault("section_style", "file_by_file_implementation")
            if result.get("code_density") == "none":
                result["code_density"] = "medium"
            _add_unique(
                contract.setdefault("required_outputs", []),
                [
                    "folder tree",
                    "source files",
                    "config files",
                    "tests",
                    "verification commands",
                    "troubleshooting checklist",
                ],
            )
            _add_unique(
                contract.setdefault("project_artifacts", []),
                [
                    "folder tree",
                    "source files",
                    "tests",
                    "config files",
                    "deployment checklist",
                ],
            )
            _add_unique(
                contract.setdefault("forbidden_content", []),
                [
                    "broken code",
                    "fake APIs",
                    "disconnected snippets",
                    "unlabeled code blocks",
                    "placeholder code",
                    "generic filler",
                ],
            )

    # ── Rule 7: Non-technical books default ──────────────────────────────
    if is_nontechnical and not _is_technical_context(result, text_pool):
        # Default no-code unless user explicitly requested code
        if not _CODE_HEAVY_PHRASES.search(text_pool) and result.get("code_density") not in ("low", "medium", "high"):
            result["code_density"] = "none"
            contract.setdefault("code_artifact_policy", "no_code")

    # ── Rule 8: Philosophy ───────────────────────────────────────────────
    if _PHILOSOPHY_KEYWORDS.search(text_pool):
        contract.setdefault("implementation_style", "argument_driven")
        contract.setdefault("section_style", "academic_argument")
        contract.setdefault("diagram_style", "argument_maps_comparison_matrices")
        if result.get("code_density") not in ("low", "medium", "high"):
            result["code_density"] = "none"
        contract.setdefault("code_artifact_policy", "no_code")
        _add_unique(
            contract.setdefault("required_outputs", []),
            [
                "definitions",
                "argument maps",
                "objections",
                "counterarguments",
                "conclusion summaries",
            ],
        )
        _add_unique(
            contract.setdefault("forbidden_content", []),
            ["fake quotes", "unsupported attribution", "unclear terminology"],
        )

    # ── Rule 9: History ──────────────────────────────────────────────────
    if _HISTORY_KEYWORDS.search(text_pool):
        if result.get("code_density") not in ("low", "medium", "high"):
            result["code_density"] = "none"
        contract.setdefault("code_artifact_policy", "no_code")
        contract.setdefault("diagram_style", "timelines_cause_effect_maps")
        _add_unique(
            contract.setdefault("required_outputs", []),
            [
                "timelines",
                "chronology tables",
                "cause-effect maps",
                "disputed interpretation notes",
            ],
        )
        _add_unique(
            contract.setdefault("forbidden_content", []),
            ["fake dates", "fake events", "invented quotes", "unsupported claims"],
        )

    # ── Rule 10: Psychology / productivity / self-help ────────────────────
    if _PSYCHOLOGY_KEYWORDS.search(text_pool):
        if result.get("code_density") not in ("low", "medium", "high"):
            result["code_density"] = "none"
        contract.setdefault("code_artifact_policy", "no_code")
        if _EVIDENCE_BASED_PHRASES.search(text_pool):
            contract.setdefault("source_strictness", "high")
        _add_unique(
            contract.setdefault("required_outputs", []),
            [
                "evidence notes",
                "exercises",
                "reflection prompts",
                "habit trackers",
                "checklists",
            ],
        )
        _add_unique(
            contract.setdefault("forbidden_content", []),
            [
                "diagnosis",
                "clinical treatment advice",
                "overclaiming causality",
                "fake studies",
                "fake statistics",
            ],
        )

    # ── Rule 11: Business ────────────────────────────────────────────────
    if _BUSINESS_KEYWORDS.search(text_pool):
        contract.setdefault("implementation_style", "case_study_playbook")
        contract.setdefault("section_style", "case_study_playbook")
        contract.setdefault("diagram_style", "frameworks_matrices_funnels")
        if result.get("code_density") not in ("low", "medium", "high"):
            result["code_density"] = "none"
        contract.setdefault("code_artifact_policy", "no_code")
        _add_unique(
            contract.setdefault("required_outputs", []),
            [
                "canvases",
                "decision tables",
                "checklists",
                "fictional case studies",
                "action plans",
            ],
        )
        _add_unique(
            contract.setdefault("forbidden_content", []),
            [
                "fake real company case studies",
                "vague startup buzzwords",
                "unsupported market claims",
            ],
        )

    # ── Rule 12: Diagram-heavy detection ─────────────────────────────────
    if _DIAGRAM_HEAVY_PHRASES.search(text_pool):
        result["diagram_density"] = "high"
        contract.setdefault("visual_policy", "structured useful diagrams only")
        _add_unique(
            contract.setdefault("forbidden_content", []),
            [
                "generic keyword diagrams",
                "internal diagram labels",
                "low-value visuals",
            ],
        )
        # Infer diagram_style by domain if missing
        if not contract.get("diagram_style"):
            if _PHILOSOPHY_KEYWORDS.search(text_pool):
                contract["diagram_style"] = "argument_maps_comparison_matrices"
            elif _HISTORY_KEYWORDS.search(text_pool):
                contract["diagram_style"] = "timelines_cause_effect_maps"
            elif _BUSINESS_KEYWORDS.search(text_pool):
                contract["diagram_style"] = "frameworks_matrices_funnels"
            elif is_technical:
                contract["diagram_style"] = "architecture_sequence_schema_deployment"
            else:
                contract["diagram_style"] = "concept_maps_decision_trees_checklists"

    # ── Rule 13: Depth inference from audience ───────────────────────────
    if not contract.get("depth_level"):
        if _BEGINNER_KEYWORDS.search(audience):
            contract["depth_level"] = "surface"
        elif _ADVANCED_KEYWORDS.search(audience):
            contract["depth_level"] = "deep"
        else:
            contract["depth_level"] = "intermediate"

    # ── Math / physics notation ──────────────────────────────────────────
    if _MATH_KEYWORDS.search(text_pool):
        contract.setdefault("notation_system", "LaTeX")

    # ── Section style inference (if still unset) ─────────────────────────
    if not contract.get("section_style"):
        book_type = result.get("book_type", "auto")
        if book_type in ("textbook", "exam_prep"):
            contract["section_style"] = "academic"
        elif book_type in ("implementation_guide", "practice_workbook"):
            contract["section_style"] = "tutorial"
        elif book_type == "reference_handbook":
            contract["section_style"] = "reference"
        elif book_type == "conceptual_guide":
            contract["section_style"] = "conversational"

    result["generation_contract"] = contract
    return result
