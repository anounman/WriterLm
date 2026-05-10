from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from reviewer.schemas import ReviewBundle, ReviewStatus, ReviewWarning

from .book_contract import BookContract
from .claim_validation import SupportStatus
from .scoring import compute_quality_score
from .validator_registry import (
    FORBIDDEN_FINAL_STRINGS,
    ValidatorReport,
    build_validator_activation_report,
    select_validators,
    validate_section_text,
)


class RepairAction(str):
    pass


class RepairPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


@dataclass
class RepairLoopResult:
    review_bundle: ReviewBundle
    qa_report: dict[str, Any]


FORBIDDEN_LINE_RE = re.compile(
    r"(?im)^\s*(?:QA gate found validation problems|Unresolved Gaps|TODO\b.*|FIXME\b.*|placeholder\b.*|citation needed\b.*|internal pipeline\b.*|debug message\b.*|validation failed\b.*)$"
)
FORBIDDEN_INLINE_RE = re.compile("|".join(re.escape(item) for item in FORBIDDEN_FINAL_STRINGS), re.I)
TEMPLATE_FILLER_RE = re.compile(r"\b(?:it is important to note that|overall,?|in conclusion,?|this section explores|as an ai|the expected result is not just that the code runs|change one input, parameter, or file|this matters because each step should fail loudly and locally|the printed output is your first test|run the code again|print statement|assertion|working code result)\b", re.I)
OVERCLAIM_REPLACEMENTS = (
    (re.compile(r"\bproves\b", re.I), "suggests"),
    (re.compile(r"\balways\b", re.I), "often"),
    (re.compile(r"\bguarantees\b", re.I), "can support"),
)


def build_repair_plan(section_text: str, validation_reports: list[Any], contract: BookContract) -> RepairPlan:
    actions: list[str] = []
    reasons: list[str] = []
    unsupported_claims: list[str] = []

    if FORBIDDEN_INLINE_RE.search(section_text):
        actions.append("remove_internal_qa_text")
        reasons.append("Forbidden internal QA/debug/placeholder text is present.")
    if TEMPLATE_FILLER_RE.search(section_text):
        actions.append("remove_repeated_template_phrase")
        reasons.append("Template filler phrase detected.")
    if (contract.code_density == "none" or not contract.code_expected) and _contains_code_artifact(section_text):
        actions.append("remove_disallowed_code")
        reasons.append("Code or software-only teaching artifacts are present in a non-code contract.")
    if re.search(r"\b(?:proves|always|guarantees)\b", section_text, re.I):
        actions.extend(["remove_or_soften_unsupported_claim", "add_uncertainty_framing"])
        reasons.append("Overclaim language detected.")
    if contract.sensitive_domain and _looks_like_sensitive_advice(section_text) and not _has_caution(section_text):
        actions.append("add_uncertainty_framing")
        reasons.append("Sensitive-domain advice needs informational caution framing.")
    if _looks_like_unmarked_case(section_text, contract):
        actions.append("mark_example_as_fictional")
        reasons.append("Business/handbook case appears fictional or illustrative but is not marked.")
    if "```" in section_text and contract.code_expected and re.search(r"\bpseudocode\b", section_text, re.I) and "conceptual pseudocode" not in section_text.casefold():
        actions.append("mark_pseudocode")
        reasons.append("Pseudocode should be marked clearly.")

    for report in validation_reports:
        claim_report = getattr(report, "claim_report", None)
        if claim_report is None and isinstance(report, dict):
            claim_report = report.get("claim_report")
        if claim_report is not None:
            results = getattr(claim_report, "results", None) or (claim_report.get("results", []) if isinstance(claim_report, dict) else [])
            for result in results:
                status = getattr(result, "support_status", None) or (result.get("support_status") if isinstance(result, dict) else None)
                claim = getattr(result, "claim", None) or (result.get("claim") if isinstance(result, dict) else None)
                if status in {SupportStatus.UNSUPPORTED, SupportStatus.CONTRADICTED, "unsupported", "contradicted"} and claim is not None:
                    text = getattr(claim, "text", None) or claim.get("text", "")
                    unsupported_claims.append(text)
            high_risk = getattr(claim_report, "high_risk_unsupported_claims", None) or (claim_report.get("high_risk_unsupported_claims", []) if isinstance(claim_report, dict) else [])
            if high_risk:
                actions.extend(["remove_or_soften_unsupported_claim", "request_research_gap_note"])
                reasons.append("Unsupported high-risk claims remain.")

        issues = getattr(report, "issues", None) or (report.get("issues", []) if isinstance(report, dict) else [])
        for issue in issues:
            repair_options = getattr(issue, "repair_options", None) or (issue.get("repair_options", []) if isinstance(issue, dict) else [])
            actions.extend(str(option) for option in repair_options)

    # ── Generation-contract-aware repair actions ─────────────────────────
    if contract.code_artifact_policy == "no_code" and _contains_code_artifact(section_text):
        if "remove_disallowed_code" not in actions:
            actions.append("remove_disallowed_code")
            reasons.append("Code artifact policy is 'no_code' but section contains code.")
    if contract.code_artifact_policy == "file_labeled_code_required" and "```" in section_text:
        if "label_code_blocks" not in actions:
            actions.append("label_code_blocks")
            reasons.append("Code blocks must be labeled with file paths when code_artifact_policy is 'file_labeled_code_required'.")
    if contract.required_stack and contract.code_expected and "```" in section_text:
        if "fix_stack_drift" not in actions:
            actions.append("fix_stack_drift")
            reasons.append("Code may use technologies outside the required stack — flag for rewrite.")
    if contract.domain_constraints and len(contract.domain_constraints) > 3:
        if "review_forbidden_content" not in actions:
            actions.append("review_forbidden_content")
            reasons.append("Forbidden content policies are defined — flag violations for rewrite.")

    ordered_actions = _dedupe(actions)
    return RepairPlan(actions=ordered_actions, unsupported_claims=_dedupe(unsupported_claims), reasons=_dedupe(reasons))


def apply_deterministic_repairs(section_text: str, repair_plan: RepairPlan, contract: BookContract) -> str:
    repaired = section_text
    if "remove_internal_qa_text" in repair_plan.actions:
        repaired = FORBIDDEN_LINE_RE.sub("", repaired)
        repaired = FORBIDDEN_INLINE_RE.sub("", repaired)

    if "remove_repeated_template_phrase" in repair_plan.actions:
        repaired = TEMPLATE_FILLER_RE.sub("", repaired)

    if "remove_disallowed_code" in repair_plan.actions or contract.code_density == "none" or not contract.code_expected:
        repaired = _remove_disallowed_code(repaired)

    if "remove_or_soften_unsupported_claim" in repair_plan.actions or "add_uncertainty_framing" in repair_plan.actions:
        for pattern, replacement in OVERCLAIM_REPLACEMENTS:
            repaired = pattern.sub(replacement, repaired)

    if "replace_fake_quote" in repair_plan.actions:
        repaired = re.sub(r"(?m)^.*(?:said|wrote|claimed):\s*['\"][^'\"]+['\"].*$", "", repaired)

    if "mark_example_as_fictional" in repair_plan.actions:
        repaired = _mark_fictional_examples(repaired)

    if "fix_domain_drift" in repair_plan.actions and not contract.code_expected:
        repaired = re.sub(r"\b(?:code validator|syntax validation|runnable code)\b", "domain-appropriate validation", repaired, flags=re.I)

    if "replace_generic_visual" in repair_plan.actions:
        repaired = re.sub(r"(?ims)^DIAGRAM:.*?(?=\n\n|\Z)", "", repaired)

    if "mark_pseudocode" in repair_plan.actions:
        repaired = re.sub(r"```(?:text|python|javascript|typescript)?\n", "```text\n# Conceptual pseudocode, not tested runnable code.\n", repaired, count=1)

    if contract.sensitive_domain and _looks_like_sensitive_advice(repaired) and not _has_caution(repaired):
        repaired = _add_sensitive_caution(repaired, contract)

    repaired = re.sub(r"[ \t]{2,}", " ", repaired)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return repaired.strip()


def _contains_code_artifact(text: str) -> bool:
    return bool(
        "```" in text
        or re.search(r"(?im)^\s*#{1,4}\s*(?:code example|output\s*/\s*expected result)\s*$", text)
        or TEMPLATE_FILLER_RE.search(text)
    )


def _remove_disallowed_code(text: str) -> str:
    repaired = re.sub(
        r"```[\s\S]*?```",
        "Practical exercise: Translate this idea into a plain-language example, worksheet, checklist, or scenario that the reader can use without programming.",
        text,
    )
    repaired = re.sub(r"(?im)^\s*#{1,4}\s*Code Example\s*$\n?", "", repaired)
    repaired = re.sub(r"(?im)^\s*#{1,4}\s*Step-by-step Implementation\s*$", "### Practical Steps", repaired)
    repaired = re.sub(r"(?im)^\s*#{1,4}\s*Output\s*/\s*Expected Result\s*$", "### Reflection Check", repaired)
    repaired = TEMPLATE_FILLER_RE.sub("", repaired)
    repaired = re.sub(
        r"(?im)^\s*(?:If the command succeeds|Treat any import error|The printed output|Save that artifact|Run and inspect the result).*$",
        "",
        repaired,
    )
    repaired = re.sub(r"(?im)^###\s*(?:Reflection Check|Practical Steps)\s*\n\s*(?=###|\Z)", "", repaired)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return repaired.strip()


def run_quality_repair_loop(
    sections: Optional[list[Any]] = None,
    contract: Optional[BookContract] = None,
    source_map: Optional[dict[str, list[dict[str, Any]]]] = None,
    max_passes: int = 2,
    *,
    review_bundle: Optional[ReviewBundle] = None,
) -> Any:
    if contract is None:
        raise ValueError("run_quality_repair_loop requires a BookContract.")
    if review_bundle is not None:
        repaired_bundle, qa_report = _run_review_bundle_loop(review_bundle, contract, source_map or {}, max_passes)
        return RepairLoopResult(review_bundle=repaired_bundle, qa_report=qa_report)
    if sections is None:
        raise ValueError("run_quality_repair_loop requires sections or review_bundle.")
    return _run_sections_loop(sections, contract, source_map or {}, max_passes)


def _run_review_bundle_loop(
    review_bundle: ReviewBundle,
    contract: BookContract,
    source_map: dict[str, list[dict[str, Any]]],
    max_passes: int,
) -> tuple[ReviewBundle, dict[str, Any]]:
    section_dicts: list[dict[str, Any]] = []
    for result in review_bundle.sections:
        synthetic_sources = []
        for index, fact in enumerate(result.section_input.supporting_facts, start=1):
            source_id = (
                result.section_input.allowed_citation_source_ids[index - 1]
                if index - 1 < len(result.section_input.allowed_citation_source_ids)
                else f"{result.section_input.section_id}_fact_{index}"
            )
            synthetic_sources.append({"source_id": source_id, "title": result.section_input.section_title, "snippet": fact})
        if synthetic_sources and result.section_input.section_id not in source_map:
            source_map[result.section_input.section_id] = synthetic_sources
        section_dicts.append({
            "id": result.section_input.section_id,
            "chapter": "",
            "section": result.section_input.section_title,
            "content": result.section_output.reviewed_content,
            "citations": result.section_output.citations_used,
        })
    repaired_sections, qa_report = _run_sections_loop(section_dicts, contract, source_map, max_passes)
    repaired_by_id = {section["id"]: section for section in repaired_sections}
    for result in review_bundle.sections:
        repaired = repaired_by_id.get(result.section_input.section_id)
        if not repaired:
            continue
        before = result.section_output.reviewed_content
        result.section_output.reviewed_content = repaired["content"]
        if before != repaired["content"]:
            if ReviewWarning.CLEANUP_ARTIFACT_FIXED not in result.section_output.reviewer_warnings:
                result.section_output.reviewer_warnings.append(ReviewWarning.CLEANUP_ARTIFACT_FIXED)
            result.section_output.applied_changes_summary.append("Applied deterministic quality repairs before assembly.")
        remaining_hard = next((r["remaining_hard_errors"] for r in qa_report["section_reports"] if r["section_id"] == result.section_input.section_id), [])
        if remaining_hard:
            result.section_output.review_status = ReviewStatus.FLAGGED
    _refresh_review_bundle_metadata(review_bundle)
    return review_bundle, qa_report


def _run_sections_loop(
    sections: list[Any],
    contract: BookContract,
    source_map: dict[str, list[dict[str, Any]]],
    max_passes: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validators = select_validators(contract)
    activation_report = build_validator_activation_report(contract, validators)
    repaired_sections = [_normalize_section(section, index) for index, section in enumerate(sections, start=1)]
    section_reports: list[dict[str, Any]] = []
    validation_reports: list[ValidatorReport] = []

    for section in repaired_sections:
        repairs_applied: list[str] = []
        remaining_hard: list[str] = []
        last_report: Optional[ValidatorReport] = None
        for _ in range(max(1, max_passes)):
            source_notes = _source_notes_for(section, source_map)
            report = validate_section_text(text=section["content"], contract=contract, source_notes=source_notes)
            last_report = report
            plan = build_repair_plan(section["content"], [report], contract)
            if not plan.actions:
                break
            repaired = apply_deterministic_repairs(section["content"], plan, contract)
            if repaired == section["content"]:
                break
            section["content"] = repaired
            repairs_applied.extend(plan.actions)

        source_notes = _source_notes_for(section, source_map)
        final_report = validate_section_text(text=section["content"], contract=contract, source_notes=source_notes)
        validation_reports.append(final_report)
        for issue in final_report.issues:
            if issue.severity == "error":
                remaining_hard.append(issue.message)
        section_reports.append({
            "section_id": section["id"],
            "chapter": section.get("chapter", ""),
            "section": section.get("section", ""),
            "issues": [issue.model_dump(mode="json") for issue in final_report.issues],
            "repairs_applied": _dedupe(repairs_applied),
            "remaining_hard_errors": remaining_hard,
            "claim_support": final_report.claim_report.model_dump(mode="json"),
            "scores": final_report.score_dimensions,
        })

    quality = compute_quality_score(validation_reports, contract)
    claim_summary = _claim_summary(validation_reports)
    qa_passed = quality.qa_passed and not any(report["remaining_hard_errors"] for report in section_reports)
    qa_report = {
        "qa_passed": qa_passed,
        "book_contract": contract.model_dump(mode="json"),
        "activated_validators": activation_report["activated_validators"],
        "validator_activation_reasons": activation_report["validator_activation_reasons"],
        "inactive_validators": activation_report["inactive_validators"],
        "repaired_sections": sum(1 for report in section_reports if report["repairs_applied"]),
        "section_reports": section_reports,
        "claim_support_summary": claim_summary,
        "scores": quality.as_report_dict(),
        "remaining_risks": _remaining_risks(section_reports),
    }
    return repaired_sections, qa_report


def _normalize_section(section: Any, index: int) -> dict[str, Any]:
    if isinstance(section, dict):
        content = str(section.get("content") or section.get("text") or section.get("reviewed_content") or "")
        return {
            "id": str(section.get("id") or section.get("section_id") or f"section_{index}"),
            "chapter": str(section.get("chapter") or chapter_from_section(section) or ""),
            "section": str(section.get("section") or section.get("title") or section.get("section_title") or f"Section {index}"),
            "content": content,
        }
    return {"id": f"section_{index}", "chapter": "", "section": f"Section {index}", "content": str(section)}


def chapter_from_section(section: dict[str, Any]) -> str:
    return str(section.get("chapter_title") or "")


def _source_notes_for(section: dict[str, Any], source_map: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return (
        source_map.get(section["id"])
        or source_map.get(section.get("section", ""))
        or source_map.get(section.get("chapter", ""))
        or []
    )


def _claim_summary(reports: list[ValidatorReport]) -> dict[str, int]:
    return {
        "total_claims": sum(report.claim_report.total_claims for report in reports),
        "supported": sum(report.claim_report.supported_count for report in reports),
        "partially_supported": sum(report.claim_report.partially_supported_count for report in reports),
        "unsupported": sum(report.claim_report.unsupported_count for report in reports),
        "contradicted": sum(report.claim_report.contradicted_count for report in reports),
    }


def _remaining_risks(section_reports: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for report in section_reports:
        for error in report["remaining_hard_errors"]:
            risks.append(f"{report['section']}: {error}")
    return risks


def _refresh_review_bundle_metadata(review_bundle: ReviewBundle) -> None:
    review_bundle.metadata.total_sections = len(review_bundle.sections)
    review_bundle.metadata.approved_sections = sum(1 for s in review_bundle.sections if s.section_output.review_status == ReviewStatus.APPROVED)
    review_bundle.metadata.revised_sections = sum(1 for s in review_bundle.sections if s.section_output.review_status == ReviewStatus.REVISED)
    review_bundle.metadata.flagged_sections = sum(1 for s in review_bundle.sections if s.section_output.review_status == ReviewStatus.FLAGGED)


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


def _looks_like_sensitive_advice(text: str) -> bool:
    return bool(re.search(r"\b(?:should|must|try|practice|avoid|therapy|treatment|diagnosis|symptoms|medication|investment|legal)\b", text, re.I))


def _has_caution(text: str) -> bool:
    return bool(re.search(r"\b(?:informational|not a substitute|professional|clinician|qualified|consult|not medical advice|not legal advice|not financial advice)\b", text, re.I))


def _add_sensitive_caution(text: str, contract: BookContract) -> str:
    if contract.domain == "psychology":
        caution = "This material is informational and is not a substitute for support from a qualified mental health professional."
    elif contract.domain == "medicine_adjacent":
        caution = "This material is informational and is not medical advice or a substitute for qualified professional care."
    else:
        caution = "This material is informational and may not apply to every situation; consult a qualified professional for personal decisions."
    return f"{caution}\n\n{text.strip()}"


def _looks_like_unmarked_case(text: str, contract: BookContract) -> bool:
    if contract.domain not in {"business", "management", "marketing"}:
        return False
    return bool(re.search(r"\b(?:case study|company|startup|client|customer)\b", text, re.I)) and not bool(re.search(r"\b(?:fictional|composite|hypothetical|illustrative)\b", text, re.I))


def _mark_fictional_examples(text: str) -> str:
    if re.search(r"\b(?:fictional|composite|hypothetical|illustrative)\b", text, re.I):
        return text
    return re.sub(r"\b(Case Study:?)", r"Fictional \1", text, count=1, flags=re.I) if re.search(r"\bCase Study", text, re.I) else f"Fictional illustrative example: {text}"
