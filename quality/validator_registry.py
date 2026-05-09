from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from .book_contract import BookContract
from .claim_validation import validate_claims


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
    qa_passed: bool = True


@dataclass(frozen=True)
class ValidatorSpec:
    name: str
    reason: str
    predicate: Callable[[BookContract], bool]


GENERIC_VALIDATORS: tuple[ValidatorSpec, ...] = (
    ValidatorSpec("source_grounding", "Every book needs important claims grounded in the available evidence.", lambda c: True),
    ValidatorSpec("claim_evidence", "Claims are classified and checked by type instead of by domain assumptions.", lambda c: True),
    ValidatorSpec("continuity", "The manuscript must preserve thesis, terminology, examples, and progression.", lambda c: True),
    ValidatorSpec("repetition", "Sections should not repeat or restart unnecessarily.", lambda c: True),
    ValidatorSpec("terminology_consistency", "Definitions and terms must remain stable once introduced.", lambda c: True),
    ValidatorSpec("placeholder_detection", "Internal QA notes, TODOs, placeholders, and prompt remnants must never ship.", lambda c: True),
    ValidatorSpec("citation_relevance", "Citations and further reading must support the nearby content.", lambda c: True),
    ValidatorSpec("chapter_to_book_alignment", "Each section must serve the Book Contract and chapter purpose.", lambda c: True),
    ValidatorSpec("audience_depth_alignment", "Depth and language must match the requested audience.", lambda c: True),
    ValidatorSpec("visual_table_relevance", "Visuals and tables must add structural value, not filler.", lambda c: True),
    ValidatorSpec("final_manuscript_polish", "The assembled book must be clean reader-facing prose.", lambda c: True),
)

OPTIONAL_VALIDATORS: tuple[ValidatorSpec, ...] = (
    ValidatorSpec("code_validator", "Activated only because the contract says code/configuration validation is needed.", lambda c: c.profile.code_validation_needed),
    ValidatorSpec("formula_validator", "Activated for math/science/formula-heavy books.", lambda c: c.profile.formula_validation_needed),
    ValidatorSpec("chronology_validator", "Activated for history and chronology-dependent manuscripts.", lambda c: c.domain == "history"),
    ValidatorSpec("argument_validator", "Activated for philosophy, essays, and argument-led books.", lambda c: c.domain == "philosophy" or c.book_type == "essay_argument"),
    ValidatorSpec("research_method_caution_validator", "Activated for psychology and social-science style evidence claims.", lambda c: c.domain in {"psychology", "education", "self_help"}),
    ValidatorSpec("safety_language_validator", "Activated for health, legal, medical, financial, or safety-sensitive content.", lambda c: c.profile.legal_medical_financial_caution_needed),
    ValidatorSpec("procedure_validator", "Activated for manuals, handbooks, implementation books, and procedural sections.", lambda c: c.book_type in {"practical_handbook", "implementation_manual", "project_based_book"} or c.profile.implementation_heavy),
    ValidatorSpec("exercise_validator", "Activated for textbooks, exam-prep books, and course/workbook formats.", lambda c: c.book_type in {"textbook", "exam_prep"}),
    ValidatorSpec("project_continuity_validator", "Activated when the book promises one running project or scenario.", lambda c: c.book_type == "project_based_book"),
    ValidatorSpec("case_study_validator", "Activated for business/practical books where examples and cases can be mistaken for real claims.", lambda c: c.domain == "business"),
)


def build_validator_registry() -> list[ValidatorSpec]:
    return list(GENERIC_VALIDATORS + OPTIONAL_VALIDATORS)


def select_validators(contract: BookContract) -> list[ValidatorActivation]:
    return [
        ValidatorActivation(name=spec.name, reason=spec.reason)
        for spec in build_validator_registry()
        if spec.predicate(contract)
    ]


FORBIDDEN_FINAL_PATTERNS = (
    r"QA gate found validation problems",
    r"\bUnresolved Gaps\b",
    r"\bTODO\b",
    r"\bplaceholder\b",
    r"citation needed",
    r"this diagram should illustrate",
    r"internal pipeline",
    r"debug message",
)

GENERIC_FILLER_DIAGRAM_RE = re.compile(r"Elements:\s*(?:Idea|Example|Result)(?:\s*,\s*(?:Idea|Example|Result))*", re.IGNORECASE)


def validate_section_text(
    *,
    text: str,
    contract: BookContract,
    source_ids: list[str] | None = None,
    citation_count: int = 0,
) -> ValidatorReport:
    activations = select_validators(contract)
    issues: list[ValidatorIssue] = []
    for pattern in FORBIDDEN_FINAL_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            issues.append(
                ValidatorIssue(
                    validator="placeholder_detection",
                    severity="error",
                    message=f"Final manuscript contains forbidden internal artifact: {pattern}",
                    repair_options=["remove_artifact", "rewrite_section", "fail_full_profile_gate"],
                )
            )
    if GENERIC_FILLER_DIAGRAM_RE.search(text):
        issues.append(
            ValidatorIssue(
                validator="visual_table_relevance",
                severity="warning",
                message="Diagram elements look generic instead of section-specific.",
                repair_options=["replace_with_concept_map", "replace_with_timeline", "remove_visual"],
            )
        )
    if not contract.profile.code_validation_needed and re.search(r"\b(?:code validator|runnable code|syntax validation)\b", text, re.IGNORECASE):
        issues.append(
            ValidatorIssue(
                validator="chapter_to_book_alignment",
                severity="warning",
                message="Non-technical contract appears to contain code-oriented validation language.",
                repair_options=["rewrite_domain_fit", "remove_technical_validator_language"],
            )
        )
    if contract.profile.legal_medical_financial_caution_needed and not re.search(r"\b(?:informational|not a substitute|professional|clinician|qualified)\b", text, re.IGNORECASE):
        issues.append(
            ValidatorIssue(
                validator="safety_language_validator",
                severity="warning",
                message="Safety-sensitive content should include careful informational framing.",
                repair_options=["add_caution_framing", "soften_claims"],
            )
        )
    claim_report = validate_claims(text, contract=contract, source_ids=source_ids, citation_count=citation_count)
    for issue in claim_report.issues:
        issues.append(
            ValidatorIssue(
                validator="claim_evidence",
                severity=issue.severity,
                message=issue.message,
                repair_options=issue.repair_options,
            )
        )
    score_dimensions = {
        "source_grounding": max(0, 100 - claim_report.unsupported_claim_count * 10),
        "claim_support": max(0, 100 - claim_report.unsupported_claim_count * 12),
        "continuity": 100,
        "domain_fit": 70 if any(i.validator == "chapter_to_book_alignment" for i in issues) else 100,
        "audience_fit": 100,
        "pedagogy_fit": 100,
        "placeholder_absence": 0 if any(i.validator == "placeholder_detection" and i.severity == "error" for i in issues) else 100,
        "visual_table_usefulness": 70 if any(i.validator == "visual_table_relevance" for i in issues) else 100,
        "factual_risk": 60 if claim_report.unsupported_claim_count else 100,
        "final_polish": 100,
    }
    return ValidatorReport(
        contract_domain=contract.domain,
        contract_book_type=contract.book_type,
        activated_validators=activations,
        issues=issues,
        score_dimensions=score_dimensions,
        qa_passed=not any(issue.severity == "error" for issue in issues),
    )
