from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quality.book_contract import BookContract, classify_book_contract
from quality.validator_registry import select_validators, validate_section_text

DEFAULT_INPUT = REPO_ROOT / "outputs" / "book.tex"
DEFAULT_CONTRACT_INPUT = REPO_ROOT / "outputs" / "book_contract.json"
DEFAULT_JSON_OUTPUT = REPO_ROOT / "outputs" / "book_evaluation.json"
DEFAULT_MD_OUTPUT = REPO_ROOT / "outputs" / "book_evaluation.md"


def evaluate_latex_book(path: Path, contract_path: Path | None = None) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    contract = _load_or_infer_contract(content, contract_path)
    sections = _extract_sections(content)
    section_evaluations = [_evaluate_section(section, contract=contract) for section in sections]
    artifact_counts = _artifact_counts(content)
    activations = select_validators(contract)

    totals = {
        "chapters": len(re.findall(r"\\chapter\{", content)),
        "sections": len(sections),
        "code_blocks": len(re.findall(r"\\begin\{lstlisting\}", content)),
        "figures": len(re.findall(r"\\begin\{figure\}", content)),
        "diagram_boxes": len(re.findall(r"\\begin\{diagramplaceholder\}", content)),
        "exercise_boxes": len(re.findall(r"\\begin\{exercisebox\}", content)),
        "gotcha_boxes": len(re.findall(r"\\begin\{gotchabox\}", content)),
        "urls": len(re.findall(r"\\url\{", content)),
        "estimated_words": _estimate_words(content),
        **artifact_counts,
    }

    weak_sections = [item for item in section_evaluations if item["score"] < 70]
    quality_score = _score_book(totals, section_evaluations, contract)

    return {
        "input_path": str(path),
        "book_contract": contract.model_dump(mode="json"),
        "activated_validators": [
            {"name": item.name, "reason": item.reason, "scope": item.scope}
            for item in activations
        ],
        "totals": totals,
        "quality_score": quality_score,
        "weak_section_count": len(weak_sections),
        "weak_sections": weak_sections[:20],
        "section_evaluations": section_evaluations,
        "recommendations": _recommendations(totals, section_evaluations, contract),
    }


def _load_or_infer_contract(content: str, contract_path: Path | None) -> BookContract:
    if contract_path and contract_path.exists():
        return BookContract.model_validate(json.loads(contract_path.read_text(encoding="utf-8")))
    title_match = re.search(r"\\title\{([^}]*)\}", content)
    title = title_match.group(1) if title_match else "Generated book"
    return classify_book_contract({"topic": title, "audience": "general readers", "goals": []})


def _extract_sections(content: str) -> list[dict[str, str]]:
    pattern = re.compile(r"\\section\{(?P<title>[^}]*)\}")
    matches = list(pattern.finditer(content))
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections.append({"title": match.group("title"), "content": content[start:end]})
    return sections


def _evaluate_section(section: dict[str, str], *, contract: BookContract) -> dict[str, Any]:
    content = section["content"]
    word_count = _estimate_words(content)
    has_code = "\\begin{lstlisting}" in content
    has_diagram = "\\begin{figure}" in content or "\\begin{diagramplaceholder}" in content
    has_exercise = "\\begin{exercisebox}" in content or re.search(r"Mini Exercise|Practice|Check for understanding", content, re.IGNORECASE)
    has_url = "\\url{" in content
    has_example = bool(re.search(r"\b(example|case|worked|scenario|timeline|objection|practice|exercise)\b", content, re.IGNORECASE))
    has_caveat = bool(re.search(r"\b(caveat|limitation|uncertain|disputed|risk|mistake|avoid|careful)\b", content, re.IGNORECASE))

    validation = validate_section_text(
        text=content,
        contract=contract,
        source_ids=["reader_facing_url"] if has_url else [],
        citation_count=1 if has_url else 0,
    )
    dimensions = dict(validation.score_dimensions)
    dimensions["audience_fit"] = _score_audience_fit(word_count, contract)
    dimensions["pedagogy_fit"] = _score_pedagogy_fit(has_example, has_exercise, has_caveat, contract)
    dimensions["example_usefulness"] = 90 if has_example else 55 if contract.book_type in {"textbook", "exam_prep", "practical_handbook", "project_based_book"} else 75
    dimensions["diagram_table_usefulness"] = _score_visuals(has_diagram, contract)
    dimensions["code_fit"] = _score_code_fit(has_code, contract)

    score = round(sum(dimensions.values()) / len(dimensions))
    hard_penalty = 0
    if any(issue["severity"] == "error" for issue in [i.model_dump(mode="json") for i in validation.issues]):
        hard_penalty += 25
    if not contract.profile.code_validation_needed and has_code and contract.domain not in {"math", "science", "machine_learning"}:
        hard_penalty += 10
    score = max(0, min(100, score - hard_penalty))

    missing = [issue.message for issue in validation.issues]
    if contract.profile.code_validation_needed and not has_code and contract.profile.implementation_heavy:
        missing.append("implementation-heavy contract likely needs code/procedure examples")
    if contract.book_type in {"textbook", "exam_prep"} and not has_exercise:
        missing.append("textbook/exam-prep contract likely needs learner practice")
    if contract.domain == "history" and not re.search(r"\b(?:1[5-9]\d{2}|20\d{2}|chronolog|before|after)\b", content, re.IGNORECASE):
        missing.append("history section lacks visible chronology markers")

    return {
        "title": section["title"],
        "score": score,
        "word_count": word_count,
        "has_code": has_code,
        "has_diagram": has_diagram,
        "has_exercise": bool(has_exercise),
        "has_reference_link": has_url,
        "dimensions": dimensions,
        "activated_validators": [item.name for item in validation.activated_validators],
        "missing": missing,
    }


def _score_book(totals: dict[str, int], sections: list[dict[str, Any]], contract: BookContract) -> int:
    if not sections:
        return 0
    avg_section_score = sum(item["score"] for item in sections) / len(sections)
    artifact_penalty = 0
    artifact_penalty += 25 if totals.get("raw_html_math_tags", 0) else 0
    artifact_penalty += 25 if totals.get("private_source_paths", 0) else 0
    artifact_penalty += 35 if totals.get("self_correction_phrases", 0) else 0
    artifact_penalty += 45 if totals.get("internal_qa_artifacts", 0) else 0
    if contract.profile.code_validation_needed and contract.profile.implementation_heavy and totals["code_blocks"] == 0:
        artifact_penalty += 20
    if not contract.profile.code_validation_needed and totals["code_blocks"] > max(1, totals["sections"] // 3):
        artifact_penalty += 10
    structure_floor = 8 if totals["chapters"] >= 3 and totals["sections"] >= 6 else 0
    return max(0, min(100, round(avg_section_score - artifact_penalty + structure_floor)))


def _recommendations(totals: dict[str, int], sections: list[dict[str, Any]], contract: BookContract) -> list[str]:
    recommendations: list[str] = []
    if totals["internal_qa_artifacts"]:
        recommendations.append("Run repair before assembly; internal QA/debug language is still present.")
    if totals["raw_html_math_tags"]:
        recommendations.append("Convert raw HTML math tags to LaTeX-safe notation.")
    if totals["private_source_paths"]:
        recommendations.append("Remove private uploaded-file paths from reader-facing prose.")
    if totals["self_correction_phrases"]:
        recommendations.append("Rewrite sections containing unresolved self-correction chatter.")
    if contract.profile.academic_source_grounding_needed and totals["urls"] == 0:
        recommendations.append("Increase source grounding for the contract's evidence standard.")
    if contract.profile.code_validation_needed and contract.profile.implementation_heavy and totals["code_blocks"] == 0:
        recommendations.append("Add runnable code/configuration or procedures because the contract promises implementation.")
    if contract.book_type in {"textbook", "exam_prep"} and totals["exercise_boxes"] == 0:
        recommendations.append("Add learner practice, checks for understanding, or exam-style rationales.")
    weak_titles = [item["title"] for item in sections if item["score"] < 70]
    if weak_titles:
        recommendations.append("Prioritize weak sections: " + ", ".join(weak_titles[:8]))
    return recommendations or ["No major recommendations."]


def _score_audience_fit(word_count: int, contract: BookContract) -> int:
    if contract.audience_level == "beginner":
        return 90 if 180 <= word_count <= 1100 else 70
    if contract.audience_level == "advanced":
        return 90 if word_count >= 350 else 55
    return 85 if word_count >= 220 else 65


def _score_pedagogy_fit(has_example: bool, has_exercise: bool, has_caveat: bool, contract: BookContract) -> int:
    score = 70
    if has_example:
        score += 10
    if has_caveat and contract.audience_level in {"advanced", "mixed"}:
        score += 10
    if has_exercise and contract.book_type in {"textbook", "exam_prep"}:
        score += 15
    if contract.domain in {"psychology", "health_adjacent", "history", "philosophy"} and has_caveat:
        score += 10
    return min(100, score)


def _score_visuals(has_diagram: bool, contract: BookContract) -> int:
    if has_diagram:
        return 85
    if contract.book_type in {"reference_handbook", "research_survey"}:
        return 80
    return 65 if contract.book_type in {"textbook", "practical_handbook", "project_based_book"} else 75


def _score_code_fit(has_code: bool, contract: BookContract) -> int:
    if contract.profile.code_validation_needed:
        return 90 if has_code or not contract.profile.implementation_heavy else 45
    return 60 if has_code else 95


def _artifact_counts(content: str) -> dict[str, int]:
    return {
        "raw_html_math_tags": len(re.findall(r"</?(?:sub|sup)>", content, flags=re.IGNORECASE)),
        "private_source_paths": len(re.findall(r"(?:file://|/app/\.cache|/Users/)", content, flags=re.IGNORECASE)),
        "self_correction_phrases": len(re.findall(r"\b(?:there appears to be an error|there was an error|previous calculation was wrong)\b", content, flags=re.IGNORECASE)),
        "internal_qa_artifacts": len(re.findall(r"\b(?:QA gate found validation problems|Unresolved Gaps|TODO|placeholder|citation needed|internal pipeline|debug message)\b", content, flags=re.IGNORECASE)),
    }


def _estimate_words(content: str) -> int:
    stripped = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", content)
    stripped = re.sub(r"[{}\\]", " ", stripped)
    return len(re.findall(r"[A-Za-z0-9_]+", stripped))


def write_outputs(evaluation: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    totals = evaluation["totals"]
    contract = evaluation["book_contract"]
    lines = [
        "# Book Evaluation",
        "",
        f"Input: `{evaluation['input_path']}`",
        f"Quality score: **{evaluation['quality_score']}/100**",
        f"Contract: **{contract['domain']} / {contract['book_type']}**",
        "",
        "## Activated Validators",
        "",
    ]
    lines.extend(f"- {item['name']}: {item['reason']}" for item in evaluation["activated_validators"])
    lines.extend([
        "",
        "## Totals",
        "",
        f"- Chapters: {totals['chapters']}",
        f"- Sections: {totals['sections']}",
        f"- Estimated words: {totals['estimated_words']}",
        f"- Code blocks: {totals['code_blocks']}",
        f"- Diagram boxes: {totals['diagram_boxes']}",
        f"- Exercise boxes: {totals['exercise_boxes']}",
        f"- Reference URLs: {totals['urls']}",
        f"- Internal QA artifacts: {totals.get('internal_qa_artifacts', 0)}",
        "",
        "## Recommendations",
        "",
    ])
    lines.extend(f"- {item}" for item in evaluation["recommendations"])
    lines.extend(["", "## Weak Sections", ""])
    weak_sections = evaluation["weak_sections"] or []
    if not weak_sections:
        lines.append("- None")
    else:
        for item in weak_sections:
            lines.append(f"- {item['title']}: {item['score']}/100")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate generated book LaTeX without compiling it.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_INPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--md-output", type=Path, default=DEFAULT_MD_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    contract_path = args.contract if args.contract.exists() else None
    evaluation = evaluate_latex_book(args.input, contract_path)
    write_outputs(evaluation, args.json_output, args.md_output)
    print(f"Quality score: {evaluation['quality_score']}/100")
    print(f"Evaluation saved to: {args.md_output}")


if __name__ == "__main__":
    main()
