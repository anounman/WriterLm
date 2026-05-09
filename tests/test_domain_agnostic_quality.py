from __future__ import annotations

from planner_agent.schemas import BookPlan, ChapterPlan, SectionContentRequirements, SectionPlan
from quality.book_contract import classify_book_contract
from quality.claim_validation import ClaimType, extract_claims
from quality.repair_loop import run_quality_repair_loop
from quality.validator_registry import select_validators
from reviewer.schemas import (
    QualityScores,
    ReviewBundle,
    ReviewBundleMetadata,
    ReviewerSectionInput,
    ReviewerSectionOutput,
    ReviewerSectionResult,
    ReviewStatus,
)


def _plan(title: str = "Test Book", *, running_project: str | None = None) -> BookPlan:
    return BookPlan(
        title=title,
        audience="beginner readers",
        tone="clear",
        depth="introductory",
        running_project=running_project,
        chapters=[
            ChapterPlan(
                chapter_number=1,
                title="Foundations",
                chapter_goal="Introduce the subject carefully.",
                sections=[
                    SectionPlan(
                        title="Core Idea",
                        goal="Explain the core idea.",
                        key_questions=["What is the core idea?"],
                        estimated_words=400,
                        content_requirements=SectionContentRequirements(must_include_example=True),
                    )
                ],
            )
        ],
    )


def _validator_names(contract) -> set[str]:
    return {item.name for item in select_validators(contract)}


def test_technical_implementation_guide_activates_code_and_procedure_validators() -> None:
    contract = classify_book_contract(
        {
            "topic": "A project-based Python API implementation guide",
            "audience": "intermediate software engineers",
            "book_type": "implementation_guide",
            "goals": ["build and validate a working API"],
            "project_based": True,
        },
        _plan("Python API Guide", running_project="One API service"),
    )

    validators = _validator_names(contract)
    assert contract.profile.code_validation_needed is True
    assert "code_validator" in validators
    assert "procedure_validator" in validators


def test_psychology_handbook_activates_research_caution_without_code_bias() -> None:
    contract = classify_book_contract(
        {
            "topic": "A psychology handbook for building healthier habits",
            "audience": "beginners",
            "book_type": "auto",
            "goals": ["distinguish research-backed claims from popular advice"],
        },
        _plan("Psychology Handbook"),
    )

    validators = _validator_names(contract)
    assert contract.domain == "psychology"
    assert contract.profile.academic_source_grounding_needed is True
    assert "research_method_caution_validator" in validators
    assert "code_validator" not in validators
    assert any("diagnosis" in item for item in contract.domain_constraints)


def test_philosophy_book_activates_argument_and_attribution_checks() -> None:
    contract = classify_book_contract(
        {
            "topic": "A philosophy book about moral responsibility and free will",
            "audience": "advanced readers",
            "book_type": "conceptual_guide",
            "goals": ["compare arguments and objections"],
        },
        _plan("Free Will and Responsibility"),
    )

    validators = _validator_names(contract)
    assert contract.domain == "philosophy"
    assert "argument_validator" in validators
    assert "code_validator" not in validators
    assert any("interpretation" in item for item in contract.domain_constraints)


def test_history_book_activates_chronology_and_source_consistency() -> None:
    contract = classify_book_contract(
        {
            "topic": "A history book on the French Revolution",
            "audience": "general readers",
            "goals": ["explain chronology and disputed interpretations"],
        },
        _plan("The French Revolution"),
    )

    validators = _validator_names(contract)
    assert contract.domain == "history"
    assert "chronology_validator" in validators
    assert contract.evidence_standard == "primary_source"


def test_beginner_textbook_activates_exercise_and_pedagogy_scaffolding() -> None:
    contract = classify_book_contract(
        {
            "topic": "A beginner textbook on algebra",
            "audience": "beginners",
            "book_type": "textbook",
            "goals": ["teach definitions, examples, and exercises"],
        },
        _plan("Algebra Textbook"),
    )

    validators = _validator_names(contract)
    assert contract.book_type == "textbook"
    assert contract.audience_level == "beginner"
    assert "exercise_validator" in validators
    assert "learning objective" in contract.structure_pattern


def test_business_handbook_activates_actionability_and_case_study_checks() -> None:
    contract = classify_book_contract(
        {
            "topic": "A practical business handbook for product strategy",
            "audience": "founders and managers",
            "goals": ["make better prioritization decisions"],
        },
        _plan("Product Strategy Handbook"),
    )

    validators = _validator_names(contract)
    assert contract.domain == "business"
    assert contract.book_type == "practical_handbook"
    assert "procedure_validator" in validators
    assert "case_study_validator" in validators


def test_project_based_book_tracks_one_running_project_scenario() -> None:
    contract = classify_book_contract(
        {
            "topic": "A project-based book on designing a museum exhibit",
            "audience": "educators",
            "project_based": True,
            "running_project_description": "One evolving museum exhibit plan",
        },
        _plan("Museum Exhibit Project", running_project="One evolving museum exhibit plan"),
    )

    validators = _validator_names(contract)
    assert contract.book_type == "project_based_book"
    assert "project_continuity_validator" in validators
    assert "running project" in contract.examples_strategy


def test_claim_extraction_classifies_dates_statistics_quotes_and_recommendations() -> None:
    contract = classify_book_contract({"topic": "A history book on 1914", "audience": "students"})
    claims = extract_claims(
        "In 1914, the crisis widened across Europe. The study included 42 participants. "
        "Readers should compare sources carefully before accepting a single interpretation of the event. "
        "\"This is a substantial quoted passage for testing.\"",
        contract=contract,
    )
    types = {claim.claim_type for claim in claims}
    assert ClaimType.HISTORICAL in types
    assert ClaimType.STATISTIC in types
    assert ClaimType.QUOTE in types
    assert ClaimType.RECOMMENDATION in types


def test_repair_loop_removes_internal_qa_artifacts_before_assembly() -> None:
    contract = classify_book_contract({"topic": "A philosophy book about ethics", "audience": "readers"})
    bundle = ReviewBundle(
        metadata=ReviewBundleMetadata(total_sections=1, approved_sections=1, revised_sections=0, flagged_sections=0),
        sections=[
            ReviewerSectionResult(
                section_input=ReviewerSectionInput(
                    section_id="s1",
                    section_title="Core Argument",
                    synthesis_status="ready",
                    central_thesis="The section explains an argument.",
                    must_include_code=False,
                    must_include_diagram=False,
                    writer_content="Draft",
                    writing_status="ready",
                    book_contract=contract.model_dump(mode="json"),
                ),
                section_output=ReviewerSectionOutput(
                    section_id="s1",
                    section_title="Core Argument",
                    reviewed_content="Good prose.\n\nQA gate found validation problems\nTODO: fix this",
                    review_status=ReviewStatus.APPROVED,
                    quality_scores=QualityScores(
                        practicality_score=7,
                        code_coverage_score=8,
                        learning_depth_score=7,
                        visual_richness_score=6,
                    ),
                ),
            )
        ],
    )

    result = run_quality_repair_loop(review_bundle=bundle, contract=contract)
    assert "QA gate" not in result.review_bundle.sections[0].section_output.reviewed_content
    assert "TODO" not in result.review_bundle.sections[0].section_output.reviewed_content
    assert result.qa_report["repaired_sections"] == 1
