from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from reviewer.schemas import ReviewBundle, ReviewStatus, ReviewWarning

from .book_contract import BookContract
from .validator_registry import ValidatorReport, select_validators, validate_section_text


FORBIDDEN_LINE_RE = re.compile(
    r"(?im)^\s*(?:QA gate found validation problems|Unresolved Gaps|TODO\b|placeholder\b|citation needed|internal pipeline|debug message).*$"
)
FORBIDDEN_INLINE_RE = re.compile(
    r"(?i)\b(?:QA gate found validation problems|citation needed|this diagram should illustrate|internal pipeline|debug message)\b"
)


@dataclass
class RepairLoopResult:
    review_bundle: ReviewBundle
    qa_report: dict[str, Any]


def run_quality_repair_loop(
    *,
    review_bundle: ReviewBundle,
    contract: BookContract,
    max_passes: int = 2,
) -> RepairLoopResult:
    """Deterministic repair pass before assembly.

    This is intentionally conservative: it removes internal artifacts, downgrades
    sections that still fail hard QA, and records a report for operators. It does
    not leak any QA text back into the manuscript.
    """

    activations = select_validators(contract)
    section_reports: list[dict[str, Any]] = []
    repaired_sections = 0

    for _ in range(max(1, max_passes)):
        changed = False
        section_reports = []
        for section in review_bundle.sections:
            output = section.section_output
            before = output.reviewed_content
            repaired = _repair_text(before)
            if repaired != before:
                output.reviewed_content = repaired
                repaired_sections += 1
                changed = True
                if ReviewWarning.CLEANUP_ARTIFACT_FIXED not in output.reviewer_warnings:
                    output.reviewer_warnings.append(ReviewWarning.CLEANUP_ARTIFACT_FIXED)
                if "Removed internal QA/debug artifacts before assembly." not in output.applied_changes_summary:
                    output.applied_changes_summary.append("Removed internal QA/debug artifacts before assembly.")

            report = validate_section_text(
                text=output.reviewed_content,
                contract=contract,
                source_ids=section.section_input.allowed_citation_source_ids,
                citation_count=len(output.citations_used),
            )
            if not report.qa_passed:
                output.review_status = ReviewStatus.FLAGGED
            section_reports.append(_report_to_dict(section.section_input.section_id, report))
        if not changed:
            break

    _refresh_review_bundle_metadata(review_bundle)
    qa_report = {
        "book_contract": contract.model_dump(mode="json"),
        "activated_validators": [item.model_dump(mode="json") for item in activations],
        "repaired_sections": repaired_sections,
        "section_reports": section_reports,
        "qa_passed": not any(
            issue.get("severity") == "error"
            for report in section_reports
            for issue in report.get("issues", [])
        ),
    }
    return RepairLoopResult(review_bundle=review_bundle, qa_report=qa_report)


def _repair_text(text: str) -> str:
    repaired = FORBIDDEN_LINE_RE.sub("", text)
    repaired = FORBIDDEN_INLINE_RE.sub("", repaired)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return repaired.strip()


def _report_to_dict(section_id: str, report: ValidatorReport) -> dict[str, Any]:
    return {
        "section_id": section_id,
        "qa_passed": report.qa_passed,
        "score_dimensions": report.score_dimensions,
        "issues": [issue.model_dump(mode="json") for issue in report.issues],
    }


def _refresh_review_bundle_metadata(review_bundle: ReviewBundle) -> None:
    review_bundle.metadata.total_sections = len(review_bundle.sections)
    review_bundle.metadata.approved_sections = sum(1 for s in review_bundle.sections if s.section_output.review_status == ReviewStatus.APPROVED)
    review_bundle.metadata.revised_sections = sum(1 for s in review_bundle.sections if s.section_output.review_status == ReviewStatus.REVISED)
    review_bundle.metadata.flagged_sections = sum(1 for s in review_bundle.sections if s.section_output.review_status == ReviewStatus.FLAGGED)
