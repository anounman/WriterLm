from quality.book_contract import classify_book_contract
from quality.repair_loop import apply_deterministic_repairs, build_repair_plan, run_quality_repair_loop
from quality.scoring import compute_quality_score
from quality.validator_registry import validate_section_text


def test_repair_removes_forbidden_qa_strings() -> None:
    contract = classify_book_contract({"topic": "A history book"})
    text = "Good prose.\nQA gate found validation problems\nUnresolved Gaps\nTODO citation needed"
    plan = build_repair_plan(text, [], contract)
    repaired = apply_deterministic_repairs(text, plan, contract)
    assert "QA gate found validation problems" not in repaired
    assert "Unresolved Gaps" not in repaired
    assert "TODO" not in repaired
    assert "citation needed" not in repaired


def test_repair_softens_overclaims() -> None:
    contract = classify_book_contract({"topic": "A psychology handbook"})
    text = "This method proves results and always guarantees improvement."
    plan = build_repair_plan(text, [], contract)
    repaired = apply_deterministic_repairs(text, plan, contract)
    assert "proves" not in repaired
    assert "always" not in repaired
    assert "guarantees" not in repaired


def test_repair_adds_sensitive_caution() -> None:
    contract = classify_book_contract({"topic": "A mental health self-help handbook"})
    text = "You should use this practice when symptoms appear."
    plan = build_repair_plan(text, [], contract)
    repaired = apply_deterministic_repairs(text, plan, contract)
    assert "informational" in repaired
    assert "qualified" in repaired or "not medical advice" in repaired


def test_repair_marks_fictional_business_examples() -> None:
    contract = classify_book_contract({"topic": "A business handbook for managers"})
    text = "Case Study: Acme reduced churn by changing its pricing."
    plan = build_repair_plan(text, [], contract)
    repaired = apply_deterministic_repairs(text, plan, contract)
    assert "Fictional" in repaired or "fictional" in repaired


def test_forbidden_strings_lower_placeholder_score() -> None:
    contract = classify_book_contract({"topic": "A philosophy book"})
    report = validate_section_text(text="Good prose. TODO citation needed.", contract=contract)
    score = compute_quality_score([report], contract)
    assert score.placeholder_cleanliness < 40


def test_unsupported_high_risk_claim_lowers_score_and_bad_book_not_above_80() -> None:
    contract = classify_book_contract({"topic": "A psychology handbook for trauma"})
    report = validate_section_text(text="Studies show that 99% of trauma is cured by this method.", contract=contract)
    score = compute_quality_score([report], contract)
    assert score.source_grounding < 60
    assert score.claim_support < 60
    assert score.overall <= 80


def test_clean_supported_section_can_score_high() -> None:
    contract = classify_book_contract({"topic": "A science explainer"})
    report = validate_section_text(
        text="Evidence suggests that photosynthesis converts light energy into chemical energy. This limitation matters when comparing plants in low-light settings.",
        contract=contract,
        source_notes=[{"source_id": "s1", "snippet": "Photosynthesis converts light energy into chemical energy in plants. This limitation matters when comparing plants in low-light settings."}],
    )
    score = compute_quality_score([report], contract)
    assert score.source_grounding >= 70
    assert score.overall >= 70


def test_repair_loop_returns_schema_and_remaining_risks() -> None:
    contract = classify_book_contract({"topic": "A psychology handbook"})
    sections = [{"section_id": "s1", "section_title": "Advice", "content": "QA gate found validation problems\nYou should always do this."}]
    repaired, report = run_quality_repair_loop(sections, contract, {}, max_passes=2)
    assert "qa_passed" in report
    assert "claim_support_summary" in report
    assert "scores" in report
    assert "QA gate" not in repaired[0]["content"]
