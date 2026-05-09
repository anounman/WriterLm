from quality.book_contract import classify_book_contract
from quality.validator_registry import select_validators


def active(topic: str):
    return {validator.name for validator in select_validators(classify_book_contract({"topic": topic}))}


def test_code_validators_do_not_activate_for_philosophy_psychology_or_history() -> None:
    assert "code_validator" not in active("A philosophy book about ethics")
    assert "code_validator" not in active("A psychology handbook about motivation")
    assert "code_validator" not in active("A history book about the Roman Republic")


def test_code_validator_activates_only_when_user_asks_for_technical_implementation() -> None:
    assert "code_validator" in active("A software implementation guide with API code")
