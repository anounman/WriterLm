from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .book_contract import BookContract


class ClaimType(str, Enum):
    FACTUAL = "factual"
    DEFINITION = "definition"
    STATISTIC = "statistic"
    QUOTE = "quote"
    RECOMMENDATION = "recommendation"
    PROCEDURE = "procedure"
    FORMULA = "formula"
    CODE_OR_CONFIG = "code_or_config"
    HISTORICAL = "historical"
    INTERPRETATION = "interpretation"
    SPECULATIVE = "speculative"

    # Backward-compatible names used by older tests/callers.
    CODE_EXAMPLE = "code_or_config"
    CONCEPTUAL = "factual"


class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NOT_CHECKED = "not_checked"


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = ""
    text: str
    claim_type: ClaimType
    risk_level: str = "low"
    needs_source: bool = False
    severity_if_unsupported: str = "warning"

    @property
    def requires_source(self) -> bool:
        return self.needs_source

    @property
    def requires_exact_support(self) -> bool:
        return self.claim_type in {ClaimType.QUOTE, ClaimType.STATISTIC, ClaimType.HISTORICAL}


ExtractedClaim = Claim


class ClaimSupportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: Claim
    support_status: SupportStatus
    supporting_source_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ClaimValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_claims: int = 0
    supported_count: int = 0
    partially_supported_count: int = 0
    unsupported_count: int = 0
    contradicted_count: int = 0
    high_risk_unsupported_claims: list[Claim] = Field(default_factory=list)
    overall_score: int = 0
    results: list[ClaimSupportResult] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.high_risk_unsupported_claims

    @property
    def claims(self) -> list[Claim]:
        return [result.claim for result in self.results]

    @property
    def unsupported_claim_count(self) -> int:
        return self.unsupported_count

    @property
    def exact_support_required_count(self) -> int:
        return sum(1 for claim in self.claims if claim.requires_exact_support)


ClaimEvidenceReport = ClaimValidationReport


CODE_FENCE_RE = re.compile(r"```(?P<lang>[A-Za-z0-9_+-]*)\n(?P<code>[\s\S]*?)```")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
QUOTE_RE = re.compile(r"(?P<quote>['\"][^'\"]{8,}['\"])")
PERCENT_OR_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent|million|billion|thousand|participants|people|studies|times|x|years?)\b", re.I)
YEAR_RE = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b")
FORMULA_RE = re.compile(r"(?:\\\(|\\\[|[∑∫√≈≤≥]|[A-Za-z]\s*=\s*[^.,;]+|[A-Za-z]\^\d|[A-Za-z]_\d)")
RESEARCH_RE = re.compile(r"\b(?:studies show|research proves|research shows|evidence suggests|trials show|scholars argue|paper reports)\b", re.I)
RECOMMEND_RE = re.compile(r"\b(?:should|must|best practice|recommend|avoid|prefer|choose|need to)\b", re.I)
PROCEDURE_RE = re.compile(r"\b(?:step|first|next|then|install|configure|run|calculate|apply|verify|create|open)\b", re.I)
SPECULATIVE_RE = re.compile(r"\b(?:may|might|could|likely|possibly|future|emerging|expected|forecast|projected)\b", re.I)
DEFINITION_RE = re.compile(r"\b(?:means|refers to|is defined as|definition|can be understood as)\b", re.I)
ATTRIBUTION_RE = re.compile(r"\b(?:argues|claimed|wrote|according to|scholars|researchers|philosophers|historians|paper|study)\b", re.I)
NEGATION_RE = re.compile(r"\b(?:not|never|no evidence|does not|did not|false|incorrect)\b", re.I)
STOPWORDS = {
    "this", "that", "with", "from", "into", "about", "their", "there", "where", "which",
    "should", "would", "could", "might", "often", "because", "while", "through", "these",
    "those", "have", "has", "had", "were", "was", "are", "the", "and", "for", "you",
}


def extract_claims(section_text: str, contract: Optional[BookContract] = None, max_claims: int = 80) -> list[Claim]:
    claims: list[Claim] = []
    for match in CODE_FENCE_RE.finditer(section_text):
        code = match.group("code").strip()
        if code:
            claims.append(_claim(f"Code/config example ({match.group('lang') or 'text'}): {code[:220]}", ClaimType.CODE_OR_CONFIG, contract, len(claims) + 1))

    prose = CODE_FENCE_RE.sub(" ", section_text)
    sentences = [s.strip() for s in SENTENCE_RE.split(prose) if len(s.strip()) >= 25]
    for sentence in sentences:
        claim_type = _classify_sentence(sentence, contract)
        if claim_type is None:
            continue
        claims.append(_claim(sentence[:700], claim_type, contract, len(claims) + 1))
        if len(claims) >= max_claims:
            break
    return claims


def match_claims_to_sources(claims: list[Claim], source_notes: list[dict[str, Any]]) -> list[ClaimSupportResult]:
    source_docs = [_normalize_source_note(note, index) for index, note in enumerate(source_notes or [], start=1)]
    results: list[ClaimSupportResult] = []
    for claim in claims:
        if not claim.needs_source:
            results.append(ClaimSupportResult(claim=claim, support_status=SupportStatus.NOT_CHECKED, reason="Claim type does not require source support.", confidence=0.5))
            continue
        if not source_docs:
            results.append(ClaimSupportResult(claim=claim, support_status=SupportStatus.UNSUPPORTED, reason="No source notes available for a source-required claim.", confidence=0.95))
            continue
        result = _match_one_claim(claim, source_docs)
        results.append(result)
    return results


def validate_claim_support(section_text: str, source_notes: list[dict[str, Any]], contract: BookContract) -> ClaimValidationReport:
    claims = extract_claims(section_text, contract=contract)
    results = match_claims_to_sources(claims, source_notes)
    supported = sum(1 for r in results if r.support_status == SupportStatus.SUPPORTED)
    partial = sum(1 for r in results if r.support_status == SupportStatus.PARTIALLY_SUPPORTED)
    unsupported = sum(1 for r in results if r.support_status == SupportStatus.UNSUPPORTED)
    contradicted = sum(1 for r in results if r.support_status == SupportStatus.CONTRADICTED)
    high_risk = [
        r.claim for r in results
        if r.support_status in {SupportStatus.UNSUPPORTED, SupportStatus.CONTRADICTED}
        and (r.claim.risk_level == "high" or r.claim.severity_if_unsupported == "error")
    ]
    checked = max(1, supported + partial + unsupported + contradicted)
    score = round(100 * ((supported + partial * 0.55) / checked) - contradicted * 20)
    if high_risk:
        score = min(score, 55)
    return ClaimValidationReport(
        total_claims=len(claims),
        supported_count=supported,
        partially_supported_count=partial,
        unsupported_count=unsupported,
        contradicted_count=contradicted,
        high_risk_unsupported_claims=high_risk,
        overall_score=max(0, min(100, score)),
        results=results,
    )


def validate_claims(
    text: str,
    *,
    contract: BookContract,
    source_ids: Optional[list[str]] = None,
    citation_count: int = 0,
) -> ClaimValidationReport:
    source_notes = [{"source_id": sid, "snippet": sid, "title": sid} for sid in (source_ids or [])]
    if citation_count and not source_notes:
        source_notes = [{"source_id": "citation_present", "snippet": "", "title": ""}]
    return validate_claim_support(text, source_notes, contract)


def _claim(text: str, claim_type: ClaimType, contract: Optional[BookContract], index: int) -> Claim:
    risk = _risk_for_claim(claim_type, contract)
    needs = _needs_source(claim_type, contract)
    severity = "error" if needs and risk == "high" else "warning"
    return Claim(
        claim_id=f"claim_{index}",
        text=" ".join(text.split()),
        claim_type=claim_type,
        risk_level=risk,
        needs_source=needs,
        severity_if_unsupported=severity,
    )


def _classify_sentence(sentence: str, contract: Optional[BookContract]) -> Optional[ClaimType]:
    if QUOTE_RE.search(sentence):
        return ClaimType.QUOTE
    if PERCENT_OR_NUMBER_RE.search(sentence):
        return ClaimType.STATISTIC
    if YEAR_RE.search(sentence) and (contract and contract.domain in {"history", "politics", "society"}):
        return ClaimType.HISTORICAL
    if FORMULA_RE.search(sentence):
        return ClaimType.FORMULA
    if RESEARCH_RE.search(sentence):
        return ClaimType.FACTUAL
    if RECOMMEND_RE.search(sentence):
        return ClaimType.PROCEDURE if PROCEDURE_RE.search(sentence) else ClaimType.RECOMMENDATION
    if PROCEDURE_RE.search(sentence):
        return ClaimType.PROCEDURE
    if DEFINITION_RE.search(sentence):
        return ClaimType.DEFINITION
    if SPECULATIVE_RE.search(sentence):
        return ClaimType.SPECULATIVE
    if ATTRIBUTION_RE.search(sentence):
        return ClaimType.INTERPRETATION if contract and contract.domain in {"philosophy", "history", "politics"} else ClaimType.FACTUAL
    if contract and contract.evidence_standard in {"research_grounded", "academic", "primary_source", "safety_sensitive"} and len(sentence.split()) >= 8:
        return ClaimType.FACTUAL
    return None


def _needs_source(claim_type: ClaimType, contract: Optional[BookContract]) -> bool:
    if claim_type in {ClaimType.STATISTIC, ClaimType.QUOTE, ClaimType.HISTORICAL, ClaimType.FACTUAL, ClaimType.INTERPRETATION}:
        return True
    if claim_type in {ClaimType.RECOMMENDATION, ClaimType.PROCEDURE}:
        return bool(contract and contract.risk_level in {"medium", "high"})
    if claim_type == ClaimType.DEFINITION:
        return bool(contract and contract.evidence_standard in {"academic", "primary_source", "safety_sensitive"})
    if claim_type == ClaimType.FORMULA:
        return bool(contract and contract.formula_expected)
    if claim_type == ClaimType.CODE_OR_CONFIG:
        return bool(contract and contract.code_expected)
    return bool(contract and contract.research_heavy)


def _risk_for_claim(claim_type: ClaimType, contract: Optional[BookContract]) -> str:
    if claim_type in {ClaimType.QUOTE, ClaimType.STATISTIC, ClaimType.HISTORICAL}:
        return "high"
    if contract and contract.sensitive_domain and claim_type in {ClaimType.RECOMMENDATION, ClaimType.FACTUAL, ClaimType.PROCEDURE}:
        return "high"
    if claim_type in {ClaimType.FACTUAL, ClaimType.INTERPRETATION, ClaimType.FORMULA, ClaimType.CODE_OR_CONFIG}:
        return "medium"
    return "low"


def _normalize_source_note(note: dict[str, Any], index: int) -> dict[str, Any]:
    source_id = str(note.get("source_id") or note.get("id") or f"source_{index}")
    title = str(note.get("title") or "")
    snippet = str(note.get("snippet") or note.get("content") or note.get("summary") or note.get("text") or "")
    return {
        "source_id": source_id,
        "title": title,
        "snippet": snippet,
        "tokens": _important_tokens(f"{title} {snippet}"),
        "numbers": _numbers(f"{title} {snippet}"),
        "years": set(YEAR_RE.findall(f"{title} {snippet}")),
        "text": f"{title} {snippet}",
    }


def _match_one_claim(claim: Claim, sources: list[dict[str, Any]]) -> ClaimSupportResult:
    claim_tokens = _important_tokens(claim.text)
    claim_numbers = _numbers(claim.text)
    claim_years = set(YEAR_RE.findall(claim.text))
    best_source: Optional[dict[str, Any]] = None
    best_score = 0.0
    best_reason = ""

    for source in sources:
        overlap = claim_tokens & source["tokens"]
        noun_score = len(overlap) / max(1, min(len(claim_tokens), 10))
        numeric_score = _numeric_score(claim_numbers, source["numbers"])
        year_score = 1.0 if claim_years and claim_years <= source["years"] else 0.0
        quote_score = _quote_score(claim.text, source["text"])

        if claim.claim_type == ClaimType.QUOTE:
            score = quote_score
            reason = "Exact quote matched." if score >= 1 else "Exact quote not found in source notes."
        elif claim.claim_type == ClaimType.STATISTIC:
            score = noun_score * 0.45 + numeric_score * 0.55
            reason = "Matched important terms and numeric evidence." if numeric_score else "Statistic lacks matching numeric evidence."
        elif claim.claim_type == ClaimType.HISTORICAL:
            score = noun_score * 0.55 + year_score * 0.45
            reason = "Matched historical terms and date/year." if year_score else "Historical claim lacks matching date/year."
        else:
            score = noun_score
            reason = f"Matched key terms: {', '.join(sorted(overlap)[:8])}" if overlap else "No meaningful key-term overlap."

        if score > best_score:
            best_score = score
            best_source = source
            best_reason = reason

    if best_source is None:
        return ClaimSupportResult(claim=claim, support_status=SupportStatus.UNSUPPORTED, reason="No comparable source text.", confidence=0.9)

    contradiction = bool(NEGATION_RE.search(best_source["text"])) != bool(NEGATION_RE.search(claim.text))
    if contradiction and best_score >= 0.45:
        return ClaimSupportResult(
            claim=claim,
            support_status=SupportStatus.CONTRADICTED,
            supporting_source_ids=[best_source["source_id"]],
            reason="Source wording appears to negate or contradict the claim.",
            confidence=min(0.9, best_score + 0.2),
        )

    if claim.claim_type == ClaimType.QUOTE:
        status = SupportStatus.SUPPORTED if best_score >= 1 else SupportStatus.UNSUPPORTED
    elif claim.claim_type in {ClaimType.STATISTIC, ClaimType.HISTORICAL}:
        status = SupportStatus.SUPPORTED if best_score >= 0.68 else SupportStatus.PARTIALLY_SUPPORTED if best_score >= 0.38 else SupportStatus.UNSUPPORTED
    else:
        status = SupportStatus.SUPPORTED if best_score >= 0.45 else SupportStatus.PARTIALLY_SUPPORTED if best_score >= 0.25 else SupportStatus.UNSUPPORTED

    return ClaimSupportResult(
        claim=claim,
        support_status=status,
        supporting_source_ids=[best_source["source_id"]] if status != SupportStatus.UNSUPPORTED else [],
        reason=best_reason,
        confidence=max(0.05, min(0.99, best_score)),
    )


def _important_tokens(text: str) -> set[str]:
    tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text)
        if token.casefold() not in STOPWORDS
    }
    return tokens


def _numbers(text: str) -> list[float]:
    values: list[float] = []
    for raw in re.findall(r"\b\d+(?:\.\d+)?\b", text):
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


def _numeric_score(claim_numbers: list[float], source_numbers: list[float]) -> float:
    if not claim_numbers:
        return 1.0
    if not source_numbers:
        return 0.0
    matched = 0
    for claim_number in claim_numbers:
        for source_number in source_numbers:
            if math.isclose(claim_number, source_number, rel_tol=0.02, abs_tol=0.01):
                matched += 1
                break
    return matched / max(1, len(claim_numbers))


def _quote_score(claim_text: str, source_text: str) -> float:
    quotes = [match.group("quote").strip("\"'") for match in QUOTE_RE.finditer(claim_text)]
    if not quotes:
        return 0.0
    source_lower = source_text.casefold()
    return 1.0 if any(quote.casefold() in source_lower for quote in quotes) else 0.0
