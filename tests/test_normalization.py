"""Deterministic tests for web.backend.normalization.normalize_book_request."""

from __future__ import annotations

import copy

import pytest

from web.backend.normalization import normalize_book_request


# ── Test 1: No-code enforcement ──────────────────────────────────────────────

def test_no_code_enforcement():
    parsed = {"topic": "Psychology handbook", "audience": "Professionals", "code_density": "none"}
    result = normalize_book_request(parsed, original_prompt="psychology handbook, no code")
    gc = result["generation_contract"]
    assert result["code_density"] == "none"
    assert gc["code_artifact_policy"] == "no_code"
    assert "code examples" in gc["forbidden_content"]
    assert "programming filler" in gc["forbidden_content"]
    assert "terminal commands" in gc["forbidden_content"]


def test_no_code_from_prompt_only():
    parsed = {"topic": "Focus habits", "audience": "Students", "code_density": "medium"}
    result = normalize_book_request(parsed, original_prompt="without code")
    gc = result["generation_contract"]
    assert result["code_density"] == "none"
    assert gc["code_artifact_policy"] == "no_code"


# ── Test 2: Showcase quality boost ───────────────────────────────────────────

def test_showcase_quality_boost():
    parsed = {"topic": "Book about learning", "audience": "General", "target_quality_score": 70}
    result = normalize_book_request(parsed, original_prompt="polished showcase book")
    gc = result["generation_contract"]
    assert result["target_quality_score"] >= 80
    assert result["auto_repair"] is True
    assert result["sample_first"] is True
    assert gc["showcase_candidate"] is True
    assert "homepage showcase-ready" in gc["success_criteria"]
    assert "no generic filler" in gc["success_criteria"]


# ── Test 3: URL extraction ──────────────────────────────────────────────────

def test_url_extraction():
    parsed = {"topic": "Web development", "audience": "Developers", "urls": ["https://fake.com"]}
    result = normalize_book_request(
        parsed,
        original_prompt="Use https://example.com/a and https://example.org/b as references.",
    )
    # Only literal URLs from the prompt — never trust LLM-generated URLs
    assert result["urls"] == ["https://example.com/a", "https://example.org/b"]


def test_url_extraction_strips_trailing_punctuation():
    parsed = {"topic": "Testing", "audience": "Devs"}
    result = normalize_book_request(
        parsed,
        original_prompt="See https://example.com/page. Also https://example.org/doc?id=1,",
    )
    assert "https://example.com/page" in result["urls"]
    assert "https://example.org/doc?id=1" in result["urls"]


# ── Test 4: Philosophy mode ─────────────────────────────────────────────────

def test_philosophy_mode():
    parsed = {"topic": "Moral philosophy and free will", "audience": "Philosophy students"}
    result = normalize_book_request(parsed, original_prompt="moral philosophy and free will")
    gc = result["generation_contract"]
    assert result["code_density"] == "none"
    assert gc["code_artifact_policy"] == "no_code"
    assert gc["implementation_style"] == "argument_driven"
    assert gc["section_style"] == "academic_argument"
    assert gc["diagram_style"] == "argument_maps_comparison_matrices"
    assert "fake quotes" in gc["forbidden_content"]
    assert "definitions" in gc["required_outputs"]
    assert "argument maps" in gc["required_outputs"]


# ── Test 5: Implementation guide mode ────────────────────────────────────────

def test_implementation_guide_mode():
    parsed = {
        "topic": "URL shortener API with FastAPI, PostgreSQL, Docker, and tests",
        "audience": "Python backend developers",
        "book_type": "implementation_guide",
        "project_based": True,
        "code_density": "high",
    }
    prompt = "Build a production-ready URL shortener API with FastAPI, PostgreSQL, Docker, and tests. Code-heavy and diagram-heavy."
    result = normalize_book_request(parsed, original_prompt=prompt)
    gc = result["generation_contract"]
    assert result["code_density"] == "high"
    assert gc["code_artifact_policy"] == "file_labeled_code_required"
    assert gc["implementation_style"] == "file_by_file"
    assert gc["section_style"] == "file_by_file_implementation"
    # Required stack extraction
    stack_lower = [s.lower() for s in gc["required_stack"]]
    assert "fastapi" in stack_lower
    assert "postgresql" in stack_lower
    assert "docker" in stack_lower
    # Note: "pytest" isn't detected because the prompt says "tests" not "pytest"
    # Project artifacts
    assert "source files" in gc["project_artifacts"]
    assert "tests" in gc["project_artifacts"]
    # Diagram-heavy
    assert result["diagram_density"] == "high"


# ── Test 6: Psychology safety ────────────────────────────────────────────────

def test_psychology_safety():
    parsed = {"topic": "Habits and focus", "audience": "General readers"}
    result = normalize_book_request(
        parsed,
        original_prompt="evidence-based psychology handbook about habits",
    )
    gc = result["generation_contract"]
    assert any("diagnosis" in item.lower() or "clinical treatment" in item.lower() for item in gc["forbidden_content"])
    assert gc.get("source_strictness") == "high"


# ── Test 7: Math notation ───────────────────────────────────────────────────

def test_math_notation():
    parsed = {"topic": "Linear algebra", "audience": "University students"}
    result = normalize_book_request(parsed, original_prompt="linear algebra textbook")
    gc = result["generation_contract"]
    assert gc["notation_system"] == "LaTeX"


# ── Test 8: Depth from audience ──────────────────────────────────────────────

def test_depth_from_audience():
    parsed = {"topic": "Machine learning", "audience": "advanced researchers"}
    result = normalize_book_request(parsed, original_prompt="")
    gc = result["generation_contract"]
    assert gc["depth_level"] == "deep"


def test_depth_beginner():
    parsed = {"topic": "Python intro", "audience": "absolute beginners with zero knowledge"}
    result = normalize_book_request(parsed, original_prompt="")
    gc = result["generation_contract"]
    assert gc["depth_level"] == "surface"


def test_depth_default():
    parsed = {"topic": "General cooking", "audience": "home cooks"}
    result = normalize_book_request(parsed, original_prompt="")
    gc = result["generation_contract"]
    assert gc["depth_level"] == "intermediate"


# ── Test 9: Idempotency ─────────────────────────────────────────────────────

def test_idempotency():
    parsed = {
        "topic": "Philosophy of free will",
        "audience": "Graduate students",
        "code_density": "none",
    }
    prompt = "polished showcase book on free will, no code"
    first = normalize_book_request(parsed, original_prompt=prompt)
    second = normalize_book_request(copy.deepcopy(first), original_prompt=prompt)
    assert first == second


# ── Test 10: Existing explicit fields not overwritten ────────────────────────

def test_existing_explicit_fields_not_overwritten():
    parsed = {
        "topic": "Machine learning",
        "audience": "advanced researchers",
        "generation_contract": {"depth_level": "surface"},
    }
    result = normalize_book_request(parsed, original_prompt="")
    gc = result["generation_contract"]
    # User explicitly set surface — normalization must not overwrite to "deep"
    assert gc["depth_level"] == "surface"


def test_existing_code_policy_not_overwritten():
    parsed = {
        "topic": "Go-to-market strategy",
        "audience": "Founders",
        "generation_contract": {"code_artifact_policy": "minimal_runnable"},
    }
    result = normalize_book_request(parsed, original_prompt="startup playbook")
    gc = result["generation_contract"]
    # User explicitly set minimal_runnable — business default "no_code" should not override it
    assert gc["code_artifact_policy"] == "minimal_runnable"


# ── Test: History mode ───────────────────────────────────────────────────────

def test_history_mode():
    parsed = {"topic": "The French Revolution", "audience": "General readers"}
    result = normalize_book_request(parsed, original_prompt="history of the French Revolution with timelines")
    gc = result["generation_contract"]
    assert result["code_density"] == "none"
    assert gc["code_artifact_policy"] == "no_code"
    assert gc["diagram_style"] == "timelines_cause_effect_maps"
    assert "fake dates" in gc["forbidden_content"]
    assert "timelines" in gc["required_outputs"]


# ── Test: Business mode ──────────────────────────────────────────────────────

def test_business_mode():
    parsed = {"topic": "Go-to-market strategy for B2B SaaS", "audience": "First-time founders"}
    result = normalize_book_request(parsed, original_prompt="startup go-to-market playbook")
    gc = result["generation_contract"]
    assert gc["implementation_style"] == "case_study_playbook"
    assert gc["section_style"] == "case_study_playbook"
    assert gc["diagram_style"] == "frameworks_matrices_funnels"
    assert gc["code_artifact_policy"] == "no_code"
    assert "canvases" in gc["required_outputs"]


# ── Test: Code-heavy detection ───────────────────────────────────────────────

def test_code_heavy_detection():
    parsed = {
        "topic": "Building a REST API",
        "audience": "Backend developers",
        "book_type": "implementation_guide",
    }
    result = normalize_book_request(parsed, original_prompt="code-heavy implementation guide")
    gc = result["generation_contract"]
    assert result["code_density"] == "high"
    assert gc["code_artifact_policy"] == "file_labeled_code_required"
    assert gc["implementation_style"] == "file_by_file"


# ── Test: Non-technical default ──────────────────────────────────────────────

def test_nontechnical_default():
    parsed = {"topic": "Meditation and mindfulness", "audience": "General public"}
    result = normalize_book_request(parsed, original_prompt="mindfulness handbook")
    gc = result["generation_contract"]
    assert result["code_density"] == "none"
    assert gc["code_artifact_policy"] == "no_code"


# ── Test: Diagram-heavy detection ────────────────────────────────────────────

def test_diagram_heavy_detection():
    parsed = {"topic": "Systems architecture", "audience": "Software engineers"}
    result = normalize_book_request(parsed, original_prompt="diagram-heavy visual architecture guide")
    gc = result["generation_contract"]
    assert result["diagram_density"] == "high"
    assert gc.get("visual_policy") == "structured useful diagrams only"


# ── Test: Required stack extraction ──────────────────────────────────────────

def test_required_stack_extraction():
    parsed = {"topic": "Web app", "audience": "Developers"}
    result = normalize_book_request(
        parsed,
        original_prompt="Build with FastAPI and PostgreSQL, deploy with Docker Compose",
    )
    gc = result["generation_contract"]
    stack_lower = [s.lower() for s in gc["required_stack"]]
    assert "fastapi" in stack_lower
    assert "postgresql" in stack_lower
    assert "docker compose" in stack_lower
