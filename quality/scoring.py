from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .book_contract import BookContract


class QualityScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: int = 0
    source_grounding: int = 0
    claim_support: int = 0
    continuity: int = 0
    audience_fit: int = 0
    pedagogy_fit: int = 0
    domain_fit: int = 0
    repetition_control: int = 0
    placeholder_cleanliness: int = 0
    visual_table_quality: int = 0
    example_quality: int = 0
    final_polish: int = 0
    qa_passed: bool = False

    def as_report_dict(self) -> dict[str, int]:
        return {
            "overall": self.overall,
            "source_grounding": self.source_grounding,
            "claim_support": self.claim_support,
            "continuity": self.continuity,
            "audience_fit": self.audience_fit,
            "pedagogy_fit": self.pedagogy_fit,
            "domain_fit": self.domain_fit,
            "repetition_control": self.repetition_control,
            "placeholder_cleanliness": self.placeholder_cleanliness,
            "visual_table_quality": self.visual_table_quality,
            "example_quality": self.example_quality,
            "final_polish": self.final_polish,
        }


DIMENSIONS = (
    "source_grounding",
    "claim_support",
    "continuity",
    "audience_fit",
    "pedagogy_fit",
    "domain_fit",
    "repetition_control",
    "placeholder_cleanliness",
    "visual_table_quality",
    "example_quality",
    "final_polish",
)

WEIGHTS = {
    "source_grounding": 0.14,
    "claim_support": 0.14,
    "continuity": 0.10,
    "audience_fit": 0.08,
    "pedagogy_fit": 0.08,
    "domain_fit": 0.10,
    "repetition_control": 0.07,
    "placeholder_cleanliness": 0.12,
    "visual_table_quality": 0.05,
    "example_quality": 0.06,
    "final_polish": 0.06,
}


def compute_quality_score(all_validation_reports: list[Any], contract: BookContract) -> QualityScore:
    if not all_validation_reports:
        return QualityScore(qa_passed=False)

    dimension_values: dict[str, list[int]] = {dimension: [] for dimension in DIMENSIONS}
    hard_errors: list[Any] = []
    high_risk_unsupported = False

    for report in all_validation_reports:
        scores = _scores_from_report(report)
        for dimension in DIMENSIONS:
            dimension_values[dimension].append(int(scores.get(dimension, 60)))
        issues = getattr(report, "issues", None) or report.get("issues", []) if isinstance(report, dict) else []
        for issue in issues:
            severity = getattr(issue, "severity", None) or (issue.get("severity") if isinstance(issue, dict) else None)
            message = getattr(issue, "message", "") or (issue.get("message", "") if isinstance(issue, dict) else "")
            if severity == "error":
                hard_errors.append(issue)
            if "High-risk claims" in message or "unsupported high-risk" in message.lower():
                high_risk_unsupported = True
        claim_report = getattr(report, "claim_report", None)
        if claim_report is not None and getattr(claim_report, "high_risk_unsupported_claims", []):
            high_risk_unsupported = True

    averaged = {
        dimension: _avg(values)
        for dimension, values in dimension_values.items()
    }

    if high_risk_unsupported:
        averaged["source_grounding"] = min(averaged["source_grounding"], 55)
        averaged["claim_support"] = min(averaged["claim_support"], 55)

    if hard_errors:
        averaged["final_polish"] = min(averaged["final_polish"], 60)

    overall = round(sum(averaged[dimension] * WEIGHTS[dimension] for dimension in DIMENSIONS))
    if hard_errors:
        overall = min(overall, 79)
    if high_risk_unsupported:
        overall = min(overall, 74)
    if averaged["placeholder_cleanliness"] < 40:
        overall = min(overall, 69)
    if averaged["domain_fit"] < 60:
        overall = min(overall, 74)

    return QualityScore(
        overall=max(0, min(100, overall)),
        qa_passed=not hard_errors,
        **{dimension: max(0, min(100, averaged[dimension])) for dimension in DIMENSIONS},
    )


def _scores_from_report(report: Any) -> dict[str, int]:
    if isinstance(report, dict):
        return dict(report.get("score_dimensions") or report.get("scores") or {})
    return dict(getattr(report, "score_dimensions", {}) or {})


def _avg(values: list[int]) -> int:
    if not values:
        return 60
    return round(sum(values) / len(values))
