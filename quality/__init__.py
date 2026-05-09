"""Domain-agnostic quality architecture for WriterLM."""

from .book_contract import (
    BookContract,
    BookContractClassifier,
    BookContractProfile,
    classify_book_contract,
)
from .claim_validation import ClaimEvidenceReport, extract_claims, validate_claims
from .scoring import QualityScore, compute_quality_score
from .validator_registry import (
    ValidatorActivation,
    ValidatorReport,
    build_validator_registry,
    select_validators,
)

__all__ = [
    "BookContract",
    "BookContractClassifier",
    "BookContractProfile",
    "ClaimEvidenceReport",
    "ValidatorActivation",
    "ValidatorReport",
    "QualityScore",
    "build_validator_registry",
    "classify_book_contract",
    "extract_claims",
    "select_validators",
    "validate_claims",
    "compute_quality_score",
]
