from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from openai import OpenAI


DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_OLLAMA_BASE_URL = "https://ollama.com/v1"
DEFAULT_OLLAMA_LOCAL_BASE_URL = "http://localhost:11434/v1"
DEFAULT_LLM_PROVIDER = "ollama"
DEFAULT_HTTP_TIMEOUT_SECONDS = 120.0

SUPPORTED_PROVIDERS = {"groq", "google", "ollama"}
GOOGLE_API_KEY_ENV_NAMES = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_AI_API_KEY",
    "GOOGLE_AI_STUDIO_API_KEY",
)
GOOGLE_AI_STUDIO_TEXT_MODEL_PREFIXES = (
    "gemini-",
    "gemma-",
    "learnlm-",
    "models/gemini-",
    "models/gemma-",
    "models/learnlm-",
)
COMMON_LEGACY_MODEL_ENV_NAMES_BY_PROVIDER = {
    "groq": ("GROQ_MODEL_NAME", "GROQ_MODEL"),
    "google": (
        "GOOGLE_MODEL_NAME",
        "GOOGLE_MODEL",
        "GEMINI_MODEL",
        "GEMINI_MODEL_NAME",
    ),
    "ollama": ("OLLAMA_MODEL_NAME", "OLLAMA_MODEL"),
}
# Ollama cloud picks: structured JSON layers get gpt-oss:120b, long-form prose
# gets deepseek-v3.1:671b, cheap condensing gets gpt-oss:20b.
DEFAULT_MODELS_BY_LAYER = {
    "planner": {
        "groq": "openai/gpt-oss-120b",
        "google": "gemini-2.5-flash-lite",
        "ollama": "gpt-oss:120b",
    },
    "researcher": {
        "groq": "openai/gpt-oss-120b",
        "google": "gemini-2.5-flash-lite",
        "ollama": "gpt-oss:120b",
    },
    "notes": {
        "groq": "llama-3.3-70b-versatile",
        "google": "gemini-2.5-flash-lite",
        "ollama": "gpt-oss:20b",
    },
    "writer": {
        "groq": "llama-3.3-70b-versatile",
        "google": "gemma-3-27b-it",
        "ollama": "deepseek-v3.1:671b",
    },
    "reviewer": {
        "groq": "openai/gpt-oss-120b",
        "google": "gemini-2.5-flash-lite",
        "ollama": "gpt-oss:120b",
    },
}


@dataclass(frozen=True)
class OpenAICompatibleProviderConfig:
    layer: str
    provider: str
    api_key: str
    base_url: str
    model: str


def _normalize_provider_name(value: str | None, *, default: str = DEFAULT_LLM_PROVIDER) -> str:
    normalized = (value or default).strip().lower()

    if normalized in {"gemini", "google", "google_ai", "google-ai"}:
        return "google"

    if normalized in SUPPORTED_PROVIDERS:
        return normalized

    supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
    raise ValueError(f"Unsupported LLM provider '{value}'. Supported providers: {supported}.")


def resolve_llm_provider(layer: str, *, default: str = DEFAULT_LLM_PROVIDER) -> str:
    layer_key = layer.upper()
    return _normalize_provider_name(
        os.getenv(f"{layer_key}_LLM_PROVIDER") or os.getenv("LLM_PROVIDER"),
        default=default,
    )


def _first_non_empty(env_names: Iterable[str]) -> str | None:
    for env_name in env_names:
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()
    return None


def _read_bool_env(*env_names: str, default: bool = False) -> bool:
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off"}
    for env_name in env_names:
        value = os.getenv(env_name)
        if value is None or not value.strip():
            continue
        normalized = value.strip().lower()
        if normalized in truthy:
            return True
        if normalized in falsy:
            return False
    return default


def _read_float_env(*env_names: str, default: float) -> float:
    for env_name in env_names:
        value = os.getenv(env_name)
        if value is None or not value.strip():
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return default


def _dedupe_env_names(env_names: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for env_name in env_names:
        if not env_name or env_name in seen:
            continue
        seen.add(env_name)
        deduped.append(env_name)
    return tuple(deduped)


def _resolve_api_key(provider: str) -> str:
    if provider == "groq":
        api_key = _first_non_empty(("GROQ_API_KEY",))
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables.")
        return api_key

    if provider == "ollama":
        # Local Ollama needs no key; the OpenAI SDK still requires a non-empty
        # string, so fall back to a placeholder when none is configured.
        return _first_non_empty(("OLLAMA_API_KEY",)) or "ollama"

    api_key = _first_non_empty(GOOGLE_API_KEY_ENV_NAMES)
    if not api_key:
        env_names = ", ".join(GOOGLE_API_KEY_ENV_NAMES)
        raise ValueError(
            "Google provider selected, but no Google API key was found. "
            f"Set one of: {env_names}."
        )
    return api_key


def _resolve_base_url(layer: str, provider: str) -> str:
    layer_key = layer.upper()

    if provider == "groq":
        return (
            _first_non_empty((f"{layer_key}_LLM_BASE_URL", "GROQ_BASE_URL"))
            or DEFAULT_GROQ_BASE_URL
        )

    if provider == "ollama":
        explicit = _first_non_empty((f"{layer_key}_LLM_BASE_URL", "OLLAMA_BASE_URL"))
        if explicit:
            return explicit
        # Cloud when a key is set, local daemon otherwise.
        if _first_non_empty(("OLLAMA_API_KEY",)):
            return DEFAULT_OLLAMA_BASE_URL
        return DEFAULT_OLLAMA_LOCAL_BASE_URL

    return (
        _first_non_empty(
            (
                f"{layer_key}_LLM_BASE_URL",
                "GOOGLE_BASE_URL",
                "GEMINI_BASE_URL",
            )
        )
        or DEFAULT_GOOGLE_BASE_URL
    )


def _layer_provider_model_env_names(layer: str, provider: str) -> tuple[str, ...]:
    layer_key = layer.upper()
    provider_key = provider.upper()
    return (
        f"{layer_key}_{provider_key}_MODEL",
        f"{layer_key}_{provider_key}_MODEL_NAME",
    )


def _provider_model_env_names(provider: str) -> tuple[str, ...]:
    provider_key = provider.upper()
    if provider == "google":
        return (
            "GOOGLE_MODEL",
            "GOOGLE_MODEL_NAME",
            "GEMINI_MODEL",
            "GEMINI_MODEL_NAME",
        )
    return (
        f"{provider_key}_MODEL",
        f"{provider_key}_MODEL_NAME",
    )


def _legacy_layer_model_env_names(layer: str) -> tuple[str, ...]:
    layer_key = layer.upper()
    return (
        f"{layer_key}_LLM_MODEL",
        f"{layer_key}_MODEL",
    )


def _resolve_model(
    layer: str,
    provider: str,
    *,
    default_models: dict[str, str],
    legacy_env_names: Iterable[str] = (),
    legacy_env_names_by_provider: dict[str, Iterable[str]] | None = None,
) -> str:
    provider_legacy_env_names = tuple((legacy_env_names_by_provider or {}).get(provider, ()))
    model_env_names = _dedupe_env_names(
        (
            *_layer_provider_model_env_names(layer, provider),
            *_provider_model_env_names(provider),
            *provider_legacy_env_names,
            *_legacy_layer_model_env_names(layer),
            *legacy_env_names,
            "LLM_MODEL",
        )
    )
    model = _first_non_empty(model_env_names)
    if model:
        validate_model_for_provider(provider, model)
        return model

    if provider not in default_models:
        raise ValueError(
            f"No default model configured for provider '{provider}' on layer '{layer}'."
        )

    model = default_models[provider]
    validate_model_for_provider(provider, model)
    return model


def validate_model_for_provider(provider: str, model: str) -> None:
    """
    Catch cross-provider model leaks before an expensive run starts.

    Google AI Studio's OpenAI-compatible endpoint serves Google model families
    such as Gemini, Gemma, and LearnLM. A Groq model ID like qwen/qwen3-32b will
    otherwise fail late with a 404 after the pipeline has already spent time and
    tokens on earlier stages.
    """
    if not _read_bool_env(
        "WRITERLM_STRICT_PROVIDER_MODELS",
        "LLM_STRICT_PROVIDER_MODELS",
        default=True,
    ):
        return

    normalized_provider = _normalize_provider_name(provider)
    normalized_model = model.strip().lower()

    if normalized_provider == "google" and not normalized_model.startswith(
        GOOGLE_AI_STUDIO_TEXT_MODEL_PREFIXES
    ):
        allowed = ", ".join(GOOGLE_AI_STUDIO_TEXT_MODEL_PREFIXES)
        raise ValueError(
            "Google provider selected, but the configured model does not look "
            f"like a Google AI Studio text model: '{model}'. Use a Gemini/Gemma "
            "model such as 'gemini-2.5-flash-lite' or 'gemma-3-27b-it'. "
            f"Accepted prefixes: {allowed}. If you intentionally use a custom "
            "Google-compatible endpoint, set WRITERLM_STRICT_PROVIDER_MODELS=0."
        )


def get_default_models_for_layer(layer: str) -> dict[str, str]:
    layer_key = layer.strip().lower()
    if layer_key not in DEFAULT_MODELS_BY_LAYER:
        supported = ", ".join(sorted(DEFAULT_MODELS_BY_LAYER))
        raise ValueError(
            f"No default models configured for layer '{layer}'. "
            f"Known layers: {supported}."
        )

    return dict(DEFAULT_MODELS_BY_LAYER[layer_key])


def get_legacy_model_env_names_by_provider(
    *,
    google_extra: Iterable[str] = (),
    groq_extra: Iterable[str] = (),
) -> dict[str, Iterable[str]]:
    return {
        "groq": (*groq_extra, *COMMON_LEGACY_MODEL_ENV_NAMES_BY_PROVIDER["groq"]),
        "google": (*google_extra, *COMMON_LEGACY_MODEL_ENV_NAMES_BY_PROVIDER["google"]),
    }


def should_trust_env_http_settings() -> bool:
    """
    Whether LLM HTTP clients should honor proxy variables from the environment.

    The Codex desktop workspace often injects a closed local proxy for sandboxed
    processes. Defaulting to False keeps direct Google/Groq API calls usable,
    while still allowing explicit proxy use with LLM_HTTP_TRUST_ENV=1.
    """
    return _read_bool_env(
        "WRITERLM_HTTP_TRUST_ENV",
        "LLM_HTTP_TRUST_ENV",
        default=False,
    )


def build_openai_client(*, api_key: str, base_url: str | None = None) -> OpenAI:
    timeout = _read_float_env(
        "WRITERLM_HTTP_TIMEOUT_SECONDS",
        "LLM_HTTP_TIMEOUT_SECONDS",
        default=DEFAULT_HTTP_TIMEOUT_SECONDS,
    )
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(
            trust_env=should_trust_env_http_settings(),
            timeout=timeout,
        ),
    )


def is_gemma_model(model: str) -> bool:
    return "gemma" in model.strip().lower()


def build_chat_messages(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> list[dict[str, Any]]:
    if is_gemma_model(model):
        return [
            {
                "role": "user",
                "content": (
                    f"{system_prompt.strip()}\n\n"
                    "User task:\n"
                    f"{user_prompt.strip()}"
                ),
            }
        ]

    return [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]


def json_response_format_kwargs(model: str) -> dict[str, Any]:
    if is_gemma_model(model):
        return {}
    return {"response_format": {"type": "json_object"}}


def resolve_openai_compatible_config(
    *,
    layer: str,
    default_models: dict[str, str],
    legacy_env_names: Iterable[str] = (),
    legacy_env_names_by_provider: dict[str, Iterable[str]] | None = None,
    default_provider: str = DEFAULT_LLM_PROVIDER,
) -> OpenAICompatibleProviderConfig:
    provider = resolve_llm_provider(layer, default=default_provider)

    return OpenAICompatibleProviderConfig(
        layer=layer,
        provider=provider,
        api_key=_resolve_api_key(provider),
        base_url=_resolve_base_url(layer, provider),
        model=_resolve_model(
            layer,
            provider,
            default_models=default_models,
            legacy_env_names=legacy_env_names,
            legacy_env_names_by_provider=legacy_env_names_by_provider,
        ),
    )


def build_openai_compatible_client(
    *,
    layer: str,
    default_models: dict[str, str],
    legacy_env_names: Iterable[str] = (),
    legacy_env_names_by_provider: dict[str, Iterable[str]] | None = None,
    default_provider: str = DEFAULT_LLM_PROVIDER,
) -> tuple[OpenAI, OpenAICompatibleProviderConfig]:
    config = resolve_openai_compatible_config(
        layer=layer,
        default_models=default_models,
        legacy_env_names=legacy_env_names,
        legacy_env_names_by_provider=legacy_env_names_by_provider,
        default_provider=default_provider,
    )
    client = build_openai_client(
        api_key=config.api_key,
        base_url=config.base_url,
    )
    return client, config
