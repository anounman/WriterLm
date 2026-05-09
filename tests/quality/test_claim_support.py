from quality.book_contract import classify_book_contract
from quality.claim_validation import SupportStatus, extract_claims, match_claims_to_sources, validate_claim_support


def test_unsupported_statistic_is_flagged() -> None:
    contract = classify_book_contract({"topic": "A psychology handbook", "audience": "beginners"})
    report = validate_claim_support("Studies show that 82% of people improve in two weeks.", [], contract)
    assert report.unsupported_count >= 1
    assert report.high_risk_unsupported_claims


def test_supported_claim_with_matching_source_passes() -> None:
    contract = classify_book_contract({"topic": "A science explainer"})
    text = "Evidence suggests that photosynthesis converts light energy into chemical energy."
    sources = [{"source_id": "s1", "title": "Photosynthesis", "snippet": "Photosynthesis converts light energy into chemical energy in plants."}]
    report = validate_claim_support(text, sources, contract)
    assert report.supported_count >= 1
    assert report.overall_score >= 70


def test_quote_without_exact_source_is_unsupported() -> None:
    contract = classify_book_contract({"topic": "A philosophy book"})
    claims = extract_claims("Kant wrote, \"This exact sentence is not in the source.\".", contract)
    results = match_claims_to_sources(claims, [{"source_id": "s1", "snippet": "Kant wrote about duty and reason."}])
    assert results[0].support_status == SupportStatus.UNSUPPORTED


def test_historical_date_without_matching_source_is_partial_or_unsupported() -> None:
    contract = classify_book_contract({"topic": "A history book about 1914"})
    report = validate_claim_support(
        "In 1914, the crisis widened across Europe.",
        [{"source_id": "s1", "snippet": "The crisis widened across Europe in 1915."}],
        contract,
    )
    assert report.unsupported_count + report.partially_supported_count >= 1
