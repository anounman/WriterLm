from __future__ import annotations

import os
from contextlib import contextmanager

from llm_provider import (
    build_chat_messages,
    get_default_models_for_layer,
    json_response_format_kwargs,
    resolve_llm_provider,
    resolve_openai_compatible_config,
)


@contextmanager
def _patched_env(updates: dict[str, str | None]):
    original = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_provider_defaults_to_google() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": None,
            "PLANNER_LLM_PROVIDER": None,
            "GROQ_API_KEY": None,
            "GROQ_MODEL_NAME": None,
            "GROQ_MODEL": None,
            "PLANNER_GROQ_MODEL": None,
            "PLANNER_GOOGLE_MODEL": None,
            "GOOGLE_API_KEY": "test-google-key",
            "GEMINI_API_KEY": None,
            "GOOGLE_AI_API_KEY": None,
            "GOOGLE_AI_STUDIO_API_KEY": None,
            "GOOGLE_MODEL_NAME": None,
            "GOOGLE_MODEL": None,
            "GEMINI_MODEL": None,
            "GEMINI_MODEL_NAME": None,
            "LLM_MODEL": None,
        }
    ):
        config = resolve_openai_compatible_config(
            layer="planner",
            default_models={"groq": "openai/gpt-oss-120b", "google": "gemini-2.5-flash"},
            legacy_env_names=("GROQ_MODEL_NAME", "GROQ_MODEL", "GOOGLE_MODEL_NAME", "GOOGLE_MODEL"),
        )

        assert resolve_llm_provider("planner") == "google"
        assert config.provider == "google"
        assert config.api_key == "test-google-key"
        assert config.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert config.model == "gemini-2.5-flash"


def test_global_groq_provider_uses_groq_credentials() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": "groq",
            "PLANNER_LLM_PROVIDER": None,
            "GROQ_API_KEY": "test-groq-key",
            "GROQ_MODEL_NAME": None,
            "GROQ_MODEL": None,
            "PLANNER_GROQ_MODEL": None,
            "PLANNER_GOOGLE_MODEL": None,
            "GOOGLE_API_KEY": "unused-google-key",
            "GEMINI_API_KEY": None,
            "GOOGLE_MODEL_NAME": None,
            "GOOGLE_MODEL": None,
            "GEMINI_MODEL": None,
            "GEMINI_MODEL_NAME": None,
            "LLM_MODEL": None,
        }
    ):
        config = resolve_openai_compatible_config(
            layer="planner",
            default_models={"groq": "openai/gpt-oss-120b", "google": "gemini-2.5-flash"},
            legacy_env_names=("GROQ_MODEL_NAME", "GROQ_MODEL", "GOOGLE_MODEL_NAME", "GOOGLE_MODEL"),
        )

        assert resolve_llm_provider("planner") == "groq"
        assert config.provider == "groq"
        assert config.api_key == "test-groq-key"
        assert config.base_url == "https://api.groq.com/openai/v1"
        assert config.model == "openai/gpt-oss-120b"


def test_global_google_provider_uses_google_credentials() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": "google",
            "GOOGLE_API_KEY": "test-google-key",
            "GOOGLE_MODEL": "gemini-custom",
            "NOTES_GOOGLE_MODEL": None,
            "NOTES_GROQ_MODEL": None,
            "GOOGLE_MODEL_NAME": None,
            "GEMINI_MODEL": None,
            "GEMINI_MODEL_NAME": None,
            "GROQ_API_KEY": "unused-groq-key",
            "GEMINI_API_KEY": None,
            "LLM_MODEL": None,
        }
    ):
        config = resolve_openai_compatible_config(
            layer="notes",
            default_models={"groq": "llama-3.3-70b-versatile", "google": "gemini-2.5-flash"},
            legacy_env_names=("GROQ_MODEL", "GROQ_MODEL_NAME", "GOOGLE_MODEL", "GOOGLE_MODEL_NAME"),
        )

        assert resolve_llm_provider("notes") == "google"
        assert config.provider == "google"
        assert config.api_key == "test-google-key"
        assert config.base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert config.model == "gemini-custom"


def test_google_ai_studio_key_alias_is_supported() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": "google",
            "GOOGLE_API_KEY": None,
            "GEMINI_API_KEY": None,
            "GOOGLE_AI_API_KEY": None,
            "GOOGLE_AI_STUDIO_API_KEY": "test-ai-studio-key",
            "GOOGLE_MODEL_NAME": None,
            "GOOGLE_MODEL": None,
            "GEMINI_MODEL": None,
            "GEMINI_MODEL_NAME": None,
            "LLM_MODEL": None,
        }
    ):
        config = resolve_openai_compatible_config(
            layer="writer",
            default_models={"groq": "llama-3.3-70b-versatile", "google": "gemini-2.5-flash"},
        )

        assert config.provider == "google"
        assert config.api_key == "test-ai-studio-key"


def test_default_writer_model_uses_gemma_for_google() -> None:
    assert get_default_models_for_layer("writer")["google"] == "gemma-3-27b-it"


def test_gemma_uses_prompt_only_json_and_single_user_message() -> None:
    messages = build_chat_messages(
        model="gemma-3-27b-it",
        system_prompt="Return JSON only.",
        user_prompt="Say ok.",
    )

    assert json_response_format_kwargs("gemma-3-27b-it") == {}
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "Return JSON only." in messages[0]["content"]
    assert "Say ok." in messages[0]["content"]


def test_gemini_keeps_json_mode_and_system_message() -> None:
    messages = build_chat_messages(
        model="gemini-2.5-flash-lite",
        system_prompt="Return JSON only.",
        user_prompt="Say ok.",
    )

    assert json_response_format_kwargs("gemini-2.5-flash-lite") == {
        "response_format": {"type": "json_object"}
    }
    assert [message["role"] for message in messages] == ["system", "user"]


def test_layer_specific_provider_override_wins() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": "groq",
            "WRITER_LLM_PROVIDER": "google",
            "GROQ_API_KEY": "test-groq-key",
            "GOOGLE_API_KEY": "test-google-key",
            "GOOGLE_MODEL_NAME": None,
            "GOOGLE_MODEL": None,
            "GEMINI_MODEL": None,
            "GEMINI_MODEL_NAME": None,
            "LLM_MODEL": None,
        }
    ):
        writer_config = resolve_openai_compatible_config(
            layer="writer",
            default_models={"groq": "llama-3.3-70b-versatile", "google": "gemini-2.5-flash"},
            legacy_env_names=("GROQ_MODEL", "GROQ_MODEL_NAME", "GOOGLE_MODEL", "GOOGLE_MODEL_NAME"),
        )
        planner_config = resolve_openai_compatible_config(
            layer="planner",
            default_models={"groq": "openai/gpt-oss-120b", "google": "gemini-2.5-flash"},
            legacy_env_names=("GROQ_MODEL_NAME", "GROQ_MODEL", "GOOGLE_MODEL_NAME", "GOOGLE_MODEL"),
        )

        assert writer_config.provider == "google"
        assert writer_config.api_key == "test-google-key"
        assert planner_config.provider == "groq"
        assert planner_config.api_key == "test-groq-key"


def test_provider_specific_google_model_wins_over_generic_reviewer_model() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": "google",
            "GOOGLE_API_KEY": "test-google-key",
            "GROQ_API_KEY": "unused-groq-key",
            "REVIEWER_GOOGLE_MODEL": "gemini-2.5-flash-lite",
            "REVIEWER_GROQ_MODEL": "qwen/qwen3-32b",
            "REVIEWER_MODEL": "qwen/qwen3-32b",
            "GOOGLE_MODEL": None,
            "GOOGLE_MODEL_NAME": None,
            "GEMINI_MODEL": None,
            "GEMINI_MODEL_NAME": None,
            "LLM_MODEL": None,
        }
    ):
        config = resolve_openai_compatible_config(
            layer="reviewer",
            default_models={"groq": "openai/gpt-oss-120b", "google": "gemini-2.5-flash"},
        )

        assert config.provider == "google"
        assert config.model == "gemini-2.5-flash-lite"


def test_groq_provider_uses_groq_layer_model_even_if_google_model_is_set() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": "groq",
            "GROQ_API_KEY": "test-groq-key",
            "GOOGLE_API_KEY": "unused-google-key",
            "REVIEWER_GOOGLE_MODEL": "gemini-2.5-flash-lite",
            "REVIEWER_GROQ_MODEL": "qwen/qwen3-32b",
            "REVIEWER_MODEL": None,
            "GROQ_MODEL": None,
            "GROQ_MODEL_NAME": None,
            "LLM_MODEL": None,
        }
    ):
        config = resolve_openai_compatible_config(
            layer="reviewer",
            default_models={"groq": "openai/gpt-oss-120b", "google": "gemini-2.5-flash"},
        )

        assert config.provider == "groq"
        assert config.model == "qwen/qwen3-32b"


def test_google_provider_rejects_groq_model_from_legacy_fallback() -> None:
    with _patched_env(
        {
            "LLM_PROVIDER": "google",
            "GOOGLE_API_KEY": "test-google-key",
            "REVIEWER_GOOGLE_MODEL": None,
            "GOOGLE_MODEL": None,
            "GOOGLE_MODEL_NAME": None,
            "GEMINI_MODEL": None,
            "GEMINI_MODEL_NAME": None,
            "REVIEWER_MODEL": "qwen/qwen3-32b",
            "LLM_MODEL": None,
            "WRITERLM_STRICT_PROVIDER_MODELS": "1",
        }
    ):
        try:
            resolve_openai_compatible_config(
                layer="reviewer",
                default_models={"groq": "openai/gpt-oss-120b", "google": "gemini-2.5-flash"},
            )
        except ValueError as exc:
            assert "Google provider selected" in str(exc)
            assert "qwen/qwen3-32b" in str(exc)
        else:
            raise AssertionError("Expected Google provider to reject a Groq/Qwen model.")
