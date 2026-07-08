from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from reviewer.schemas import ReviewBundle


IMAGE_BLOCK_PATTERN = re.compile(
    r"^DIAGRAM:\s*(?P<hint>.+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)

IMAGE_EXTENSIONS_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
}


@dataclass
class ImageAsset:
    asset_id: str
    section_id: str
    title: str
    prompt: str
    file_path: str
    source_kind: str
    source_url: str | None = None
    source_description: str | None = None


@dataclass
class ImageAssetResult:
    enabled: bool
    created: list[ImageAsset]
    warnings: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "created": [asdict(item) for item in self.created],
            "warnings": list(self.warnings),
        }


def image_assets_enabled() -> bool:
    return _read_bool_env("WRITERLM_IMAGE_ASSETS_ENABLED", default=True)


def prepare_image_assets_for_review_bundle(
    *,
    review_bundle: ReviewBundle,
    run_dir: Path,
    book_title: str,
) -> ImageAssetResult:
    if not image_assets_enabled():
        return ImageAssetResult(enabled=False, created=[], warnings=[])

    assets_dir = run_dir / "assets" / "images"
    assets_dir.mkdir(parents=True, exist_ok=True)

    max_assets = _read_int_env("WRITERLM_MAX_IMAGE_ASSETS", default=4, minimum=0)
    if max_assets <= 0:
        return ImageAssetResult(enabled=False, created=[], warnings=["Image asset limit is 0."])

    created: list[ImageAsset] = []
    warnings: list[str] = []

    for section_result in review_bundle.sections:
        if len(created) >= max_assets:
            break

        output = section_result.section_output
        match = IMAGE_BLOCK_PATTERN.search(output.reviewed_content)
        if not match:
            continue

        hint = match.group("hint").strip()
        title = _image_title_from_hint(hint, fallback=output.section_title)
        prompt = _build_image_prompt(
            book_title=book_title,
            section_title=output.section_title,
            hint=hint,
            content=output.reviewed_content,
        )
        asset_id = f"img_{len(created) + 1:03d}_{_safe_slug(output.section_id)}"

        asset = None
        if _read_bool_env("WRITERLM_WEB_IMAGE_SEARCH_ENABLED", default=True):
            asset, web_warnings = _try_web_image_asset(
                asset_id=asset_id,
                section_id=output.section_id,
                title=title,
                prompt=prompt,
                assets_dir=assets_dir,
            )
            warnings.extend(web_warnings)

        if asset is None and _read_bool_env("WRITERLM_GENERATED_IMAGES_ENABLED", default=True):
            asset, generation_warning = _try_google_generated_image(
                asset_id=asset_id,
                section_id=output.section_id,
                title=title,
                prompt=prompt,
                assets_dir=assets_dir,
            )
            if generation_warning:
                warnings.append(generation_warning)

        if asset is None:
            continue

        output.reviewed_content = _inject_image_block(
            content=output.reviewed_content,
            image_path=asset.file_path,
            title=asset.title,
            source_kind=asset.source_kind,
            source_url=asset.source_url,
        )
        created.append(asset)

    manifest_path = run_dir / "image_assets.json"
    manifest_path.write_text(
        json.dumps(
            {"created": [asdict(item) for item in created], "warnings": warnings},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ImageAssetResult(enabled=True, created=created, warnings=warnings)


def _try_web_image_asset(
    *,
    asset_id: str,
    section_id: str,
    title: str,
    prompt: str,
    assets_dir: Path,
) -> tuple[ImageAsset | None, list[str]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return None, ["Tavily key missing; skipped web image search."]

    try:
        from tavily import TavilyClient

        response = TavilyClient(api_key=api_key).search(
            query=f"{prompt} educational diagram image",
            max_results=4,
            search_depth="basic",
            include_images=True,
            include_image_descriptions=True,
        )
    except Exception as exc:
        return None, [f"Tavily image search failed for {section_id}: {exc}"]

    image_candidates = _extract_image_candidates(response)
    warnings: list[str] = []
    for index, candidate in enumerate(image_candidates[:6], start=1):
        url = candidate.get("url") or ""
        description = candidate.get("description") or ""
        downloaded = _download_image(url, assets_dir / f"{asset_id}_web_{index}")
        if downloaded is None:
            continue
        return (
            ImageAsset(
                asset_id=asset_id,
                section_id=section_id,
                title=title,
                prompt=prompt,
                file_path=str(downloaded),
                source_kind="web",
                source_url=url,
                source_description=description,
            ),
            warnings,
        )

    warnings.append(f"No downloadable web image found for {section_id}.")
    return None, warnings


def _try_google_generated_image(
    *,
    asset_id: str,
    section_id: str,
    title: str,
    prompt: str,
    assets_dir: Path,
) -> tuple[ImageAsset | None, str | None]:
    # Image generation always uses Google, independent of the text LLM provider.
    api_key = _first_env("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY", "GOOGLE_AI_STUDIO_API_KEY")
    if not api_key:
        return None, "Google key missing; skipped generated image."

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        model = os.getenv("WRITERLM_IMAGE_MODEL", "gemini-2.5-flash-image")
        response = client.models.generate_content(
            model=model,
            contents=[_generation_prompt(prompt)],
        )
        image_bytes, mime_type = _extract_generated_image_bytes(response)
        if not image_bytes:
            return None, f"Google image model returned no image for {section_id}."

        extension = IMAGE_EXTENSIONS_BY_MIME.get(mime_type or "image/png", ".png")
        path = assets_dir / f"{asset_id}_generated{extension}"
        path.write_bytes(image_bytes)
        return (
            ImageAsset(
                asset_id=asset_id,
                section_id=section_id,
                title=title,
                prompt=prompt,
                file_path=str(path),
                source_kind="generated_google",
                source_description=f"Generated with {model}; SynthID watermark expected.",
            ),
            None,
        )
    except ImportError:
        return None, "google-genai is not installed; skipped generated image."
    except Exception as exc:
        return None, f"Google image generation failed for {section_id}: {exc}"


def _extract_generated_image_bytes(response: Any) -> tuple[bytes | None, str | None]:
    parts = getattr(response, "parts", None)
    if parts is None:
        candidates = getattr(response, "candidates", []) or []
        parts = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts.extend(getattr(content, "parts", []) or [])

    for part in parts or []:
        inline_data = getattr(part, "inline_data", None)
        if inline_data is None:
            continue
        data = getattr(inline_data, "data", None)
        mime_type = getattr(inline_data, "mime_type", None) or "image/png"
        if isinstance(data, bytes):
            return data, mime_type
        if isinstance(data, str):
            return base64.b64decode(data), mime_type
    return None, None


def _extract_image_candidates(response: Any) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    def add_image(value: Any) -> None:
        if isinstance(value, str):
            candidates.append({"url": value, "description": ""})
        elif isinstance(value, dict):
            url = str(value.get("url") or "").strip()
            if url:
                candidates.append({"url": url, "description": str(value.get("description") or "").strip()})

    if isinstance(response, dict):
        for item in response.get("images") or []:
            add_image(item)
        for result in response.get("results") or []:
            if isinstance(result, dict):
                for item in result.get("images") or []:
                    add_image(item)

    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for candidate in candidates:
        url = candidate["url"]
        if url in seen:
            continue
        seen.add(url)
        deduped.append(candidate)
    return deduped


def _download_image(url: str, target_stem: Path) -> Path | None:
    if not url.lower().startswith(("http://", "https://")):
        return None
    try:
        response = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "WriterLM image asset resolver/1.0"},
            stream=True,
        )
        response.raise_for_status()
    except Exception:
        return None

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    extension = IMAGE_EXTENSIONS_BY_MIME.get(content_type)
    if extension is None:
        guessed = mimetypes.guess_extension(content_type or "")
        extension = guessed if guessed in {".jpg", ".jpeg", ".png"} else None
    if extension is None:
        return None

    data = response.content
    if len(data) < 1024 or len(data) > _read_int_env("WRITERLM_MAX_IMAGE_BYTES", default=6_000_000, minimum=1024):
        return None

    path = target_stem.with_suffix(".jpg" if extension == ".jpeg" else extension)
    path.write_bytes(data)
    return path


def _inject_image_block(
    *,
    content: str,
    image_path: str,
    title: str,
    source_kind: str,
    source_url: str | None,
) -> str:
    source = source_url or ("AI-generated image via Google Gemini" if source_kind == "generated_google" else "Image source unavailable")
    block = "\n".join(
        [
            f"IMAGE: {image_path}",
            f"Caption: {title}",
            f"Source: {source}",
            "",
        ]
    )
    return IMAGE_BLOCK_PATTERN.sub(block.rstrip(), content, count=1)


def _image_title_from_hint(hint: str, *, fallback: str) -> str:
    cleaned = hint.strip(" -")
    match = re.match(r"^\[[^\]]+\]\s*-\s*(.+)$", cleaned)
    if match:
        return match.group(1).strip()[:120] or fallback
    return cleaned[:120] or fallback


def _build_image_prompt(*, book_title: str, section_title: str, hint: str, content: str) -> str:
    context = " ".join(line.strip() for line in content.splitlines()[:8] if line.strip())
    return (
        f"Book: {book_title}. Section: {section_title}. Visual need: {hint}. "
        f"Context: {context[:500]}"
    )


def _generation_prompt(prompt: str) -> str:
    return (
        "Generate one clean educational illustration for a textbook. "
        "Use a simple, original, non-photorealistic style. Avoid logos, brand marks, watermarks, and tiny text. "
        "The image should explain the concept visually and be suitable for inclusion in a LaTeX PDF. "
        f"{prompt}"
    )


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    return slug[:60] or "section"


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _read_bool_env(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_int_env(name: str, *, default: int, minimum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)
