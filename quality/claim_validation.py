from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .book_contract import BookContract


class ClaimType(str, Enum):
    FACTUAL = "factual_claim"
    DEFINITION = "definition"
    STATISTIC = "statistic"
    QUOTE = "quote"
    INTERPRETATION = "interpretation"
    RECOMMENDATION = "recommendation"
    PROCEDURE = "procedure"
    FORMULA = "formula"
    CODE_EXAMPLE = "code/example"
    HISTORICAL = "historical_claim"
    CONCEPTUAL = "conceptual_explanation"
    SPECULATIVE = "speculative/future-looking_claim"


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    claim_type: ClaimType
    requires_source: bool = True
    requires_exact_support: bool = False
    validation_strategy: str = ""


class ClaimValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_type: ClaimType
    severity: str = "warning"
    message: str
    repair_options: list[str] = Field(default_factory=list)


class ClaimEvidenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    claims: list[ExtractedClaim] = Field(default_factory=list)
    issues: list[ClaimValidationIssue] = Field(default_factory=list)
    unsupported_claim_count: int = 0
    exact_support_required_count: int = 0


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
QUOTE_RE = re.compile(r"['\"][^'\"]{12,}['\"]")
STAT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent|million|billion|thousand|times|x|years?|people|participants|studies)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(?:1[5-9]\d{2}|20\d{2})\b")
FORMULA_RE = re.compile(r"(?:\\\(|\\\[|\b[A-Za-z]\s*=|[∑∫√≈≤≥]|[A-Za-z]\^\d|[A-Za-z]_\d)")
SPEC_RE = re.compile(r"\b(?:may|might|could|likely|future|emerging|expected|projected|forecast|speculative)\b", re.IGNORECASE)
RECOMMEND_RE = re.compile(r"\b(?:should|must|recommend|best practice|use|avoid|choose|prefer)\b", re.IGNORECASE)
PROCEDURE_RE = re.compile(r"\b(?:step|first|next|then|install|configure|run|calculate|apply|verify)\b", re.IGNORECASE)


def extract_claims(text: str, *, contract: BookContract | None = None, max_claims: int = 40) -> list[ExtractedClaim]:
    claims: list[ExtractedClaim] = []
    cleaned = re.sub(r"```[\s\S]*?```", " CODE_EXAMPLE_BLOCK ", text)
    candidates = [item.strip() for item in SENTENCE_RE.split(cleaned) if len(item.strip()) >= 35]
    for index, sentence in enumerate(candidates[: max_claims * 2], start=1):
        claim_type = _classify_sentence(sentence, contract)
        requires_source = _requires_source(claim_type, contract)
        claims.append(
            ExtractedClaim(
                claim_id=f"claim_{index}",
                text=sentence[:500],
                claim_type=claim_type,
                requires_source=requires_source,
                requires_exact_support=claim_type in {ClaimType.QUOTE, ClaimType.STATISTIC, ClaimType.HISTORICAL},
                validation_strategy=_strategy_for(claim_type, contract),
            )
        )
        if len(claims) >= max_claims:
            break
    return claims


def validate_claims(
    text: str,
    *,
    contract: BookContract,
    source_ids: list[str] | None = None,
    citation_count: int = 0,
) -> ClaimEvidenceReport:
    claims = extract_claims(text, contract=contract)
    available_support = bool(source_ids) or citation_count > 0
    issues: list[ClaimValidationIssue] = []
    for claim in claims:
        if claim.requires_source and not available_support:
            issues.append(
                ClaimValidationIssue(
                    claim_id=claim.claim_id,
                    claim_type=claim.claim_type,
                    severity="error" if contract.evidence_standard in {"academic", "primary_source", "safety_sensitive"} else "warning",
                    message=f"{claim.claim_type.value} needs source support under the {contract.evidence_standard} evidence standard.",
                    repair_options=["research_more", "soften_claim", "mark_uncertainty", "remove_claim", "fail_full_profile_gate"],
                )
            )
        if claim.claim_type == ClaimType.SPECULATIVE and not SPEC_RE.search(claim.text):
            issues.append(
                ClaimValidationIssue(
                    claim_id=claim.claim_id,
                    claim_type=claim.claim_type,
                    message="Speculative claim should be explicitly framed as uncertain or future-looking.",
                    repair_options=["mark_uncertainty", "soften_claim"],
                )
            )
    return ClaimEvidenceReport(
        ok=not any(issue.severity == "error" for issue in issues),
        claims=claims,
        issues=issues,
        unsupported_claim_count=len(issues),
        exact_support_required_count=sum(1 for claim in claims if claim.requires_exact_support),
    )


def _classify_sentence(sentence: str, contract: BookContract | None) -> ClaimType:
    lowered = sentence.casefold()
    if "code_example_block" in lowered:
        return ClaimType.CODE_EXAMPLE
    if QUOTE_RE.search(sentence):
        return ClaimType.QUOTE
    if STAT_RE.search(sentence):
        return ClaimType.STATISTIC
    if contract and contract.domain == "history" and DATE_RE.search(sentence):
        return ClaimType.HISTORICAL
    if FORMULA_RE.search(sentence):
        return ClaimType.FORMULA
    if SPEC_RE.search(sentence):
        return ClaimType.SPECULATIVE
    if RECOMMEND_RE.search(sentence):
        return ClaimType.RECOMMENDATION
    if PROCEDURE_RE.search(sentence):
        return ClaimType.PROCEDURE
    if re.search(r"\b(?:means|refers to|is defined as|definition)\b", sentence, re.IGNORECASE):
        return ClaimType.DEFINITION
    if contract and contract.domain == "philosophy" and re.search(r"\b(?:argues|interpret|objection|therefore|premise)\b", sentence, re.IGNORECASE):
        return ClaimType.INTERPRETATION
    if re.search(r"\b(?:because|therefore|explains|shows|implies)\b", sentence, re.IGNORECASE):
        return ClaimType.CONCEPTUAL
    return ClaimType.FACTUAL


def _requires_source(claim_type: ClaimType, contract: BookContract | None) -> bool:
    if claim_type in {ClaimType.CODE_EXAMPLE, ClaimType.FORMULA, ClaimType.PROCEDURE}:
        return bool(contract and contract.evidence_standard in {"academic", "primary_source", "safety_sensitive"})
    if claim_type in {ClaimType.QUOTE, ClaimType.STATISTIC, ClaimType.HISTORICAL, ClaimType.FACTUAL}:
        return True
    return bool(contract and contract.evidence_standard in {"academic", "primary_source", "research_grounded", "safety_sensitive"})


def _strategy_for(claim_type: ClaimType, contract: BookContract | None) -> str:
    if claim_type == ClaimType.QUOTE:
        return "verify exact source wording and attribution"
    if claim_type == ClaimType.STATISTIC:
        return "verify source, date, denominator, population, and context"
    if claim_type == ClaimType.HISTORICAL:
        return "verify chronology, actors, dates, and primary/secondary source consistency"
    if claim_type == ClaimType.PROCEDURE:
        return "check ordered steps, prerequisites, and internal consistency"
    if claim_type == ClaimType.CODE_EXAMPLE:
        return "syntax/runtime validation only if code is present and runnable"
    if claim_type == ClaimType.FORMULA:
        return "check notation, derivation, and worked-example consistency"
    if claim_type == ClaimType.INTERPRETATION:
        return "attribute interpretation and separate it from established scholarship"
    if claim_type == ClaimType.RECOMMENDATION and contract and contract.risk_level != "low":
        return "connect recommendation to evidence and include safety/caution framing"
    return "check source support and framing appropriate to the contract"
