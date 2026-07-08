"""
LLM-driven per-layer model routing.

Given the book request (topic/domain/audience) and the models actually
available on the configured provider, one cheap LLM call assigns the best
model to each pipeline layer (planner, researcher, notes, writer, reviewer).
Falls back to the static defaults in llm_provider.DEFAULT_MODELS_BY_LAYER on
any failure, so routing can never break a run.

Enable with WRITERLM_AUTO_MODEL_ROUTING=1. The chosen models are exported as
{LAYER}_{PROVIDER}_MODEL env vars, which every layer already reads.
"""

from __future__ import annotations

import json
import os
from typing import Any

from llm_provider import (
    DEFAULT_MODELS_BY_LAYER,
    build_openai_client,
    build_chat_messages,
    json_response_format_kwargs,
    resolve_llm_provider,
    resolve_openai_compatible_config,
)

LAYERS = ("planner", "researcher", "notes", "writer", "reviewer")

LAYER_NEEDS = {
    "planner": "structured JSON output, outline/curriculum reasoning",
    "researcher": "structured JSON output, query planning, evidence extraction",
    "notes": "cheap fast summarization/condensing into structured notes",
    "writer": "high-quality long-form prose, domain accuracy, narrative flow",
    "reviewer": "critical analysis, instruction following, structured JSON output",
}

# Capability hints for model families the router may see. Free-text; the
# router LLM uses these plus its own knowledge.
MODEL_FAMILY_HINTS = {
    "nemotron": "strong at math and scientific reasoning",
    "deepseek": "strong general reasoning and long-form writing",
    "qwen3-coder": "strong at code generation",
    "qwen": "good multilingual generalist",
    "gpt-oss": "reliable structured/JSON output, good general reasoning",
    "kimi": "strong long-form creative and technical writing",
    "glm": "good generalist with solid reasoning",
    "llama": "solid generalist",
    "gemma": "small fast generalist",
    "gemini": "strong generalist with reliable JSON output",
}

ROUTER_SYSTEM_PROMPT = (
    "You assign LLM models to stages of a book-generation pipeline. "
    "Pick the best model for each stage from the available list only. "
    "Consider the book's domain (e.g. math-heavy books favor models strong at math, "
    "programming books favor code-strong models, narrative books favor strong prose models). "
    "Prefer cheaper/smaller models for the 'notes' stage. "
    'Return JSON only: {"planner": "<model>", "researcher": "<model>", '
    '"notes": "<model>", "writer": "<model>", "reviewer": "<model>", "rationale": "<one sentence>"}'
)


def _strip_json_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences despite response_format."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def auto_model_routing_enabled() -> bool:
    value = os.getenv("WRITERLM_AUTO_MODEL_ROUTING", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _fallback_models(provider: str) -> dict[str, str]:
    return {
        layer: DEFAULT_MODELS_BY_LAYER[layer].get(
            provider, next(iter(DEFAULT_MODELS_BY_LAYER[layer].values()))
        )
        for layer in LAYERS
    }


def _describe_models(models: list[str]) -> str:
    lines = []
    for model in models:
        hint = next(
            (note for family, note in MODEL_FAMILY_HINTS.items() if family in model.lower()),
            "",
        )
        lines.append(f"- {model}" + (f" ({hint})" if hint else ""))
    return "\n".join(lines)


def list_available_models(provider: str | None = None) -> list[str]:
    """List model IDs from the provider's OpenAI-compatible /models endpoint."""
    provider = provider or resolve_llm_provider("planner")
    config = resolve_openai_compatible_config(
        layer="planner",
        default_models=DEFAULT_MODELS_BY_LAYER["planner"],
    )
    client = build_openai_client(api_key=config.api_key, base_url=config.base_url)
    return sorted(model.id for model in client.models.list())


def route_models_for_book(
    *,
    topic: str,
    audience: str = "",
    goals: str = "",
    provider: str | None = None,
    available_models: list[str] | None = None,
) -> dict[str, str]:
    """
    Return {layer: model} for the given book. Never raises: falls back to
    static defaults on any failure.
    """
    provider = provider or resolve_llm_provider("planner")
    fallback = _fallback_models(provider)

    try:
        models = available_models or list_available_models(provider)
        if not models:
            return fallback

        config = resolve_openai_compatible_config(
            layer="planner",
            default_models=DEFAULT_MODELS_BY_LAYER["planner"],
        )
        client = build_openai_client(api_key=config.api_key, base_url=config.base_url)

        needs = "\n".join(f"- {layer}: {desc}" for layer, desc in LAYER_NEEDS.items())
        user_prompt = (
            f"Book topic: {topic}\n"
            f"Audience: {audience or 'general'}\n"
            f"Goals: {goals or 'n/a'}\n\n"
            f"Pipeline stages and needs:\n{needs}\n\n"
            f"Available models:\n{_describe_models(models)}"
        )
        response = client.chat.completions.create(
            model=config.model,
            temperature=0.0,
            messages=build_chat_messages(
                model=config.model,
                system_prompt=ROUTER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            ),
            **json_response_format_kwargs(config.model),
        )
        payload: dict[str, Any] = json.loads(
            _strip_json_fences(response.choices[0].message.content or "{}")
        )
    except Exception:
        return fallback

    available = set(models)
    routed = {}
    for layer in LAYERS:
        candidate = str(payload.get(layer) or "").strip()
        routed[layer] = candidate if candidate in available else fallback[layer]
    return routed


def apply_routed_models_to_env(routed: dict[str, str], *, provider: str | None = None) -> None:
    """Export routing decisions as the env vars every layer already reads."""
    provider_key = (provider or resolve_llm_provider("planner")).upper()
    for layer, model in routed.items():
        os.environ[f"{layer.upper()}_{provider_key}_MODEL"] = model


def maybe_route_models(planner_input: dict[str, Any]) -> dict[str, str] | None:
    """
    Entry point for pipelines: route + apply if enabled, else no-op.
    Returns the routing decision (for logging) or None when disabled.
    """
    if not auto_model_routing_enabled():
        return None
    routed = route_models_for_book(
        topic=str(planner_input.get("topic") or planner_input.get("title") or ""),
        audience=str(planner_input.get("target_audience") or planner_input.get("audience") or ""),
        goals=str(planner_input.get("goals") or ""),
    )
    apply_routed_models_to_env(routed)
    return routed


if __name__ == "__main__":
    # ponytail: self-check with offline fallback path only (no network).
    os.environ.setdefault("WRITERLM_AUTO_MODEL_ROUTING", "1")
    fallback = _fallback_models("ollama")
    assert set(fallback) == set(LAYERS)
    assert fallback["writer"] == "deepseek-v3.1:671b"
    routed = route_models_for_book(topic="Linear Algebra", available_models=[])
    assert routed == fallback, routed
    print("model_router self-check OK")
