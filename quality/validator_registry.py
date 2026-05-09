from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from .book_contract import BookContract
from .claim_validation import ClaimValidationReport, SupportStatus, validate_claim_support


@dataclass(frozen=True)
class ValidatorSpec:
    name: str
    reason: str
    predicate: Callable[[BookContract], bool]
    scope: str = "section"


class ValidatorActivation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    reason: str
    scope: str = "section"


class ValidatorIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validator: str
    severity: str = "warning"
    message: str
    repair_options: list[str] = Field(default_factory=list)


class ValidatorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_domain: str
    contract_book_type: str
    activated_validators: list[ValidatorActivation] = Field(default_factory=list)
    issues: list[ValidatorIssue] = Field(default_factory=list)
    score_dimensions: dict[str, int] = Field(default_factory=dict)
    claim_report: ClaimValidationReport = Field(default_factory=ClaimValidationReport)
    qa_passed: bool = True


GENERIC_VALIDATOR_NAMES = (
    "source_grounding",
    "claim_evidence",
    "continuity",
    "repetition",
    "terminology_consistency",
    "placeholder_detection",
    "citation_relevance",
    "chapter_alignment",
    "audience_depth_alignment",
    "visual_table_relevance",
    "final_polish",
)


GENERIC_VALIDATORS: tuple[ValidatorSpec, ...] = tuple(
    ValidatorSpec(name, "Generic validator: required for every domain and book type.", lambda c: True)
    for name in GENERIC_VALIDATOR_NAMES
)


OPTIONAL_VALIDATORS: tuple[ValidatorSpec, ...] = (
    ValidatorSpec("code_validator", "Activated only when the contract expects code or implementation-heavy procedures.", lambda c: c.code_expected or c.implementation_heavy),
    ValidatorSpec("formula_validator", "Activated only when the contract expects formulas, proofs, math, or quantitative validation.", lambda c: c.formula_expected),
    ValidatorSpec("chronology_validator", "Activated for history, politics, society, or chronology-heavy books.", lambda c: c.domain in {"history", "politics", "society"}),
    ValidatorSpec("argument_validator", "Activated for philosophy, ethics, or argumentative books.", lambda c: c.domain in {"philosophy", "ethics"} or c.book_type == "argumentative"),
    ValidatorSpec("research_method_caution_validator", "Activated for psychology, social science, science, education, self-help, or research-heavy books.", lambda c: c.domain in {"psychology", "science", "education", "self_help"} or c.research_heavy),
    ValidatorSpec("safety_language_validator", "Activated for sensitive medical, mental-health, legal, financial, or high-risk domains.", lambda c: c.sensitive_domain),
    ValidatorSpec("procedure_validator", "Activated for manuals, handbooks, implementation guides, and implementation-heavy books.", lambda c: c.book_type in {"manual", "practical_handbook", "implementation_guide", "implementation_manual"} or c.implementation_heavy),
    ValidatorSpec("exercise_validator", "Activated for textbooks and exam-prep books.", lambda c: c.book_type in {"textbook", "exam_prep"}),
    ValidatorSpec("project_continuity_validator", "Activated for project-based books.", lambda c: c.project_based or c.book_type in {"project_based", "project_based_book"}),
    ValidatorSpec("case_study_validator", "Activated for business, management, and marketing books.", lambda c: c.domain in {"business", "management", "marketing"}),
)


FORBIDDEN_FINAL_STRINGS = (
    "QA gate found validation problems",
    "Unresolved Gaps",
    "TODO",
    "FIXME",
    "placeholder",
    "citation needed",
    "this diagram should illustrate",
    "internal pipeline",
    "debug message",
    "validation failed",
)
FORBIDDEN_RE = re.compile("|".join(re.escape(item) for item in FORBIDDEN_FINAL_STRINGS), re.I)
GENERIC_VISUAL_RE = re.compile(r"(?:DIAGRAM|TABLE):.*(?:Idea\s*/\s*Example\s*/\s*Result|Idea,\s*Example,\s*Result|generic visual|this diagram should illustrate)", re.I | re.S)
TEMPLATE_PHRASES = (
    "it is important to note",
    "overall",
    "in conclusion",
    "this section explores",
    "as an ai",
    "the expected result is not just that the code runs",
    "change one input, parameter, or file",
    "this matters because each step should fail loudly and locally",
    "the printed output is your first test",
)


def build_validator_registry() -> list[ValidatorSpec]:
    return list(GENERIC_VALIDATORS + OPTIONAL_VALIDATORS)


def select_validators(contract: BookContract) -> list[ValidatorSpec]:
    return [spec for spec in build_validator_registry() if spec.predicate(contract)]


def build_validator_activation_report(contract: BookContract, validators: list[ValidatorSpec]) -> dict[str, Any]:
    active_names = {validator.name for validator in validators}
    inactive = [spec for spec in build_validator_registry() if spec.name not in active_names]
    return {
        "activated_validators": [validator.name for validator in validators],
        "validator_activation_reasons": {validator.name: validator.reason for validator in validators},
        "inactive_validators": [validator.name for validator in inactive],
        "inactive_reasons": {validator.name: _inactive_reason(validator, contract) for validator in inactive},
    }


def validate_section_text(
    *,
    text: str,
    contract: BookContract,
    source_ids: list[str] | None = None,
    citation_count: int = 0,
    source_notes: list[dict[str, Any]] | None = None,
) -> ValidatorReport:
    validators = select_validators(contract)
    activations = [ValidatorActivation(name=spec.name, reason=spec.reason, scope=spec.scope) for spec in validators]
    notes = list(source_notes or [])
    if not notes and source_ids:
        notes = [{"source_id": sid, "title": sid, "snippet": sid} for sid in source_ids]
    if citation_count and not notes:
        notes = [{"source_id": "citation_present", "title": "", "snippet": ""}]

    claim_report = validate_claim_support(text, notes, contract)
    issues = _detect_issues(text, contract, claim_report)
    dimensions = _dimension_scores(text, contract, claim_report, issues)
    hard_errors = [issue for issue in issues if issue.severity == "error"]
    return ValidatorReport(
        contract_domain=contract.domain,
        contract_book_type=contract.book_type,
        activated_validators=activations,
        issues=issues,
        score_dimensions=dimensions,
        claim_report=claim_report,
        qa_passed=not hard_errors,
    )


def _inactive_reason(spec: ValidatorSpec, contract: BookContract) -> str:
    if spec.name == "code_validator":
        return "Inactive because BookContract does not expect code and is not implementation-heavy."
    if spec.name == "formula_validator":
        return "Inactive because BookContract does not expect formulas."
    if spec.name == "chronology_validator":
        return "Inactive because BookContract is not history/politics/society."
    if spec.name == "argument_validator":
        return "Inactive because BookContract is not philosophy/ethics/argumentative."
    if spec.name == "safety_language_validator":
        return "Inactive because BookContract is not sensitive-domain."
    return "Inactive because the BookContract predicate did not match."


def _detect_issues(text: str, contract: BookContract, claim_report: ClaimValidationReport) -> list[ValidatorIssue]:
    issues: list[ValidatorIssue] = []
    if FORBIDDEN_RE.search(text):
        issues.append(ValidatorIssue(
            validator="placeholder_detection",
            severity="error",
            message="Final text contains forbidden QA/debug/placeholder strings.",
            repair_options=["remove_internal_qa_text"],
        ))
    if claim_report.high_risk_unsupported_claims:
        issues.append(ValidatorIssue(
            validator="claim_evidence",
            severity="error",
            message="High-risk claims remain unsupported or contradicted.",
            repair_options=["remove_or_soften_unsupported_claim", "add_uncertainty_framing", "request_research_gap_note"],
        ))
    if contract.sensitive_domain and _looks_like_advice(text) and not _has_caution_framing(text):
        issues.append(ValidatorIssue(
            validator="safety_language_validator",
            severity="error",
            message="Sensitive-domain advice lacks caution/informational framing.",
            repair_options=["add_uncertainty_framing"],
        ))
    if not contract.code_expected and not contract.implementation_heavy and re.search(r"\b(?:code validator|syntax validation|runnable code)\b", text, re.I):
        issues.append(ValidatorIssue(
            validator="chapter_alignment",
            severity="error",
            message="Text drifts into code-oriented validation language for a non-technical contract.",
            repair_options=["fix_domain_drift"],
        ))
    if contract.implementation_heavy and contract.code_expected and "```" not in text and re.search(r"\b(?:run|install|configure|api|command)\b", text, re.I):
        issues.append(ValidatorIssue(
            validator="code_validator",
            severity="error",
            message="Implementation-heavy technical section discusses runnable work without code/configuration.",
            repair_options=["request_research_gap_note", "mark_pseudocode"],
        ))
    if GENERIC_VISUAL_RE.search(text):
        issues.append(ValidatorIssue(
            validator="visual_table_relevance",
            severity="warning",
            message="Visual/table appears generic or prompt-like.",
            repair_options=["replace_generic_visual"],
        ))
    if _template_phrase_count(text) >= 4:
        issues.append(ValidatorIssue(
            validator="repetition",
            severity="warning",
            message="Repeated template phrases reduce manuscript quality.",
            repair_options=["remove_repeated_template_phrase"],
        ))
    if contract.audience_level == "advanced" and _looks_shallow(text):
        issues.append(ValidatorIssue(
            validator="audience_depth_alignment",
            severity="warning",
            message="Advanced audience requested but section appears shallow or template-heavy.",
            repair_options=["improve_audience_depth"],
        ))
    if _fictional_case_unmarked(text, contract):
        issues.append(ValidatorIssue(
            validator="case_study_validator",
            severity="warning",
            message="Case/example may be fictional but is not clearly marked.",
            repair_options=["mark_example_as_fictional"],
        ))
    return issues


def _dimension_scores(text: str, contract: BookContract, claim_report: ClaimValidationReport, issues: list[ValidatorIssue]) -> dict[str, int]:
    forbidden = bool(FORBIDDEN_RE.search(text))
    high_risk = bool(claim_report.high_risk_unsupported_claims)
    domain_drift = any(issue.validator == "chapter_alignment" and issue.severity == "error" for issue in issues)
    generic_visual = any(issue.validator == "visual_table_relevance" for issue in issues)
    repetition_count = _template_phrase_count(text)
    shallow = _looks_shallow(text)

    source_grounding = max(0, min(100, claim_report.overall_score))
    claim_support = source_grounding
    if high_risk:
        source_grounding = min(source_grounding, 55)
        claim_support = min(claim_support, 55)

    return {
        "source_grounding": source_grounding,
        "claim_support": claim_support,
        "continuity": 75 if domain_drift else 85,
        "audience_fit": 55 if contract.audience_level == "advanced" and shallow else 82,
        "pedagogy_fit": 70 if shallow else 84,
        "domain_fit": 50 if domain_drift else 84,
        "repetition_control": max(35, 90 - repetition_count * 12),
        "placeholder_cleanliness": 25 if forbidden else 95,
        "visual_table_quality": 50 if generic_visual else 80,
        "example_quality": 65 if _fictional_case_unmarked(text, contract) else 78,
        "final_polish": 50 if forbidden else 82,
    }


def _looks_like_advice(text: str) -> bool:
    return bool(re.search(r"\b(?:should|must|try|use|avoid|practice|therapy|treatment|diagnosis|symptoms|investment|legal)\b", text, re.I))


def _has_caution_framing(text: str) -> bool:
    return bool(re.search(r"\b(?:informational|not a substitute|professional|clinician|qualified|consult|may not apply|not medical advice|not legal advice|not financial advice)\b", text, re.I))


def _template_phrase_count(text: str) -> int:
    lowered = text.casefold()
    return sum(lowered.count(phrase) for phrase in TEMPLATE_PHRASES)


def _looks_shallow(text: str) -> bool:
    words = re.findall(r"[A-Za-z]+", text)
    nuance = re.search(r"\b(?:trade-off|limitation|edge case|evidence|counterargument|uncertainty|failure mode|interpretation|methodology)\b", text, re.I)
    return len(words) < 180 or not nuance


def _fictional_case_unmarked(text: str, contract: BookContract) -> bool:
    if contract.domain not in {"business", "management", "marketing"}:
        return False
    has_case = bool(re.search(r"\b(?:case study|company|startup|customer|firm)\b", text, re.I))
    marked = bool(re.search(r"\b(?:fictional|composite|hypothetical|illustrative)\b", text, re.I))
    return has_case and not marked
