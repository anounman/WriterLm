from quality.book_contract import classify_book_contract
from quality.validator_registry import build_validator_activation_report, select_validators


def names(contract):
    return {validator.name for validator in select_validators(contract)}


def test_psychology_handbook_activates_social_science_and_safety() -> None:
    contract = classify_book_contract({
        "topic": "A psychology handbook for anxiety habits",
        "audience": "beginners",
        "goals": ["research-backed practical advice"],
    })
    active = names(contract)
    assert contract.domain == "psychology"
    assert contract.sensitive_domain is True
    assert "research_method_caution_validator" in active
    assert "safety_language_validator" in active
    assert "code_validator" not in active


def test_philosophy_book_activates_argument_not_code() -> None:
    contract = classify_book_contract({
        "topic": "A philosophy book on ethics and moral responsibility",
        "audience": "advanced readers",
    })
    active = names(contract)
    assert "argument_validator" in active
    assert "code_validator" not in active


def test_history_book_activates_chronology() -> None:
    contract = classify_book_contract({"topic": "A history book about the French Revolution"})
    assert "chronology_validator" in names(contract)


def test_technical_guide_activates_code_and_procedure() -> None:
    contract = classify_book_contract({
        "topic": "A software API implementation guide with code",
        "book_type": "implementation guide",
    })
    active = names(contract)
    assert "code_validator" in active
    assert "procedure_validator" in active


def test_business_handbook_activates_case_study_and_procedure() -> None:
    contract = classify_book_contract({"topic": "A practical business strategy handbook"})
    active = names(contract)
    assert "case_study_validator" in active
    assert "procedure_validator" in active


def test_beginner_textbook_activates_exercise() -> None:
    contract = classify_book_contract({"topic": "A beginner textbook for algebra", "audience": "beginner students"})
    active = names(contract)
    assert contract.audience_level == "beginner"
    assert "exercise_validator" in active


def test_project_based_book_activates_project_continuity() -> None:
    contract = classify_book_contract({"topic": "A project-based book about museum exhibit design", "project_based": True})
    assert "project_continuity_validator" in names(contract)


def test_activation_report_lists_inactive_validators() -> None:
    contract = classify_book_contract({"topic": "A philosophy book on epistemology"})
    validators = select_validators(contract)
    report = build_validator_activation_report(contract, validators)
    assert "argument_validator" in report["activated_validators"]
    assert "code_validator" in report["inactive_validators"]
