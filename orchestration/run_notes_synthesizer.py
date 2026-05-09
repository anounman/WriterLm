from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

from notes_synthesizer.graph import build_notes_synthesizer_graph, initialize_state
from notes_synthesizer.llm import GroqStructuredLLM
from notes_synthesizer.schemas import SynthesisStatus
from llm_provider import (
    get_default_models_for_layer,
    get_legacy_model_env_names_by_provider,
    resolve_openai_compatible_config,
)
from notes_synthesizer.state import (
    NotesSynthesizerInput,
    NotesSynthesizerSectionTask,
    NotesSynthesizerState,
)


INPUT_PATH = REPO_ROOT / "runs" / "research_bundle.json"
OUTPUT_PATH = REPO_ROOT / "outputs" / "notes_bundle.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Research bundle not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(f"Research bundle must be a JSON object: {path}")

    return payload


def build_tasks_from_research_bundle(
    bundle: dict[str, Any],
    *,
    book_state: dict[str, Any] | None = None,
) -> list[NotesSynthesizerSectionTask]:
    tasks: list[NotesSynthesizerSectionTask] = []

    book_plan = bundle.get("book_plan") or {}
    book_contract = bundle.get("book_contract") if isinstance(bundle.get("book_contract"), dict) else {}
    planner_chapters = book_plan.get("chapters") if isinstance(book_plan, dict) else []
    chapter_map: dict[str, dict[str, Any]] = {}
    planner_section_map: dict[str, dict[str, Any]] = {}

    if isinstance(planner_chapters, list):
        for chapter in planner_chapters:
            if not isinstance(chapter, dict):
                continue

            chapter_title = _clean_string(chapter.get("title"))
            chapter_number = chapter.get("chapter_number")
            chapter_goal = _clean_string(chapter.get("chapter_goal"))
            sections = chapter.get("sections")
            if not isinstance(sections, list):
                continue

            for section in sections:
                if not isinstance(section, dict):
                    continue

                section_title = _clean_string(section.get("title"))
                section_goal = _clean_string(section.get("goal"))
                section_id = _build_section_id(
                    chapter_number=chapter_number,
                    section_title=section_title,
                )

                planner_section_map[section_id] = {
                    "section_id": section_id,
                    "section_title": section_title or "Untitled Section",
                    "section_objective": section_goal or "No planner objective available.",
                    "chapter_title": chapter_title,
                    "chapter_goal": chapter_goal,
                    "key_concepts": _as_string_list(section.get("key_questions")),
                    "content_requirements": section.get("content_requirements") or {},
                    "book_state": book_state or {"book_contract": book_contract},
                }

    chapters = bundle.get("chapters")
    if not isinstance(chapters, list):
        return tasks

    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue

        chapter_title = _clean_string(chapter.get("chapter_title"))
        section_packets = chapter.get("section_packets")
        if not isinstance(section_packets, list):
            continue

        for packet in section_packets:
            if not isinstance(packet, dict):
                continue

            section_id = _clean_string(packet.get("section_id"))
            section_title = _clean_string(packet.get("section_title"))
            objective = _clean_string(packet.get("objective"))
            chapter_id = _clean_string(packet.get("chapter_id"))

            if not section_id:
                section_id = _build_section_id_from_packet(packet)
            if not section_id:
                continue

            planner_section = dict(planner_section_map.get(section_id, {}))
            if not planner_section:
                planner_section = {
                    "section_id": section_id,
                    "section_title": section_title or "Untitled Section",
                    "section_objective": objective or "No planner objective available.",
                    "chapter_title": chapter_title,
                    "chapter_id": chapter_id,
                    "key_concepts": [],
                    "book_state": book_state or {"book_contract": book_contract},
                }

            research_section = {
                "section_id": section_id,
                "section_title": section_title or planner_section.get("section_title") or "Untitled Section",
                "section_objective": objective or planner_section.get("section_objective") or "No section objective available.",
                "key_concepts": _as_string_list(packet.get("key_concepts")),
                "evidence_items": packet.get("evidence_items") if isinstance(packet.get("evidence_items"), list) else [],
                "knowledge_map": packet.get("knowledge_map") if isinstance(packet.get("knowledge_map"), dict) else {},
                "writing_guidance": _as_string_list(packet.get("writing_guidance")),
                "open_questions": _as_string_list(packet.get("open_questions")),
                "coverage_report": packet.get("coverage_report"),
                "source_references": (
                    packet.get("source_references")
                    if isinstance(packet.get("source_references"), list)
                    else packet.get("sources")
                    if isinstance(packet.get("sources"), list)
                    else []
                ),
            }

            tasks.append(
                NotesSynthesizerSectionTask(
                    section_id=section_id,
                    section_title=research_section["section_title"],
                    planner_section_ref=planner_section,
                    research_section_ref=research_section,
                )
            )

    return tasks


def save_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _slugify(value: str | None) -> str:
    if not value:
        return "untitled"
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    slug = "-".join(part for part in cleaned.split("-") if part)
    return slug or "untitled"


def _build_section_id(*, chapter_number: Any, section_title: str | None) -> str | None:
    try:
        chapter_num = int(chapter_number)
    except (TypeError, ValueError):
        chapter_num = None

    if chapter_num is None or not section_title:
        return None

    return f"chapter-{chapter_num}-section-{_slugify(section_title)}"


def _build_section_id_from_packet(packet: dict[str, Any]) -> str | None:
    chapter_id = _clean_string(packet.get("chapter_id"))
    section_title = _clean_string(packet.get("section_title"))
    if not chapter_id or not section_title:
        return None
    return f"{chapter_id}-section-{_slugify(section_title)}"


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            cleaned = _clean_string(item)
            if cleaned:
                output.append(cleaned)
        return output
    cleaned = _clean_string(value)
    return [cleaned] if cleaned else []


def main() -> None:
    start_time = time.time()
    bundle = load_json(INPUT_PATH)
    tasks = build_tasks_from_research_bundle(bundle)

    if not tasks:
        print("No Notes Synthesizer tasks could be built from the research bundle.")
        raise SystemExit(1)

    llm_config = resolve_openai_compatible_config(
        layer="notes",
        default_models=get_default_models_for_layer("notes"),
        legacy_env_names_by_provider=get_legacy_model_env_names_by_provider(),
    )
    llm = GroqStructuredLLM(
        api_key=llm_config.api_key,
        model=llm_config.model,
        base_url=llm_config.base_url,
    )

    input_data = NotesSynthesizerInput(
        book_id="test_run",
        book_title="Test Book",
        tasks=tasks,
    )

    graph = build_notes_synthesizer_graph(llm)
    state = initialize_state(input_data)
    final_state_raw = graph.invoke(state)
    final_state = NotesSynthesizerState.model_validate(final_state_raw)

    if final_state.output_bundle is None:
        raise RuntimeError("Notes Synthesizer completed without producing an output bundle.")

    save_output(
        OUTPUT_PATH,
        final_state.output_bundle.model_dump(mode="json"),
    )

    ready_count = sum(
        1
        for note in final_state.output_bundle.section_notes
        if note.synthesis_status == SynthesisStatus.READY
    )
    partial_count = sum(
        1
        for note in final_state.output_bundle.section_notes
        if note.synthesis_status == SynthesisStatus.PARTIAL
    )
    blocked_count = sum(
        1
        for note in final_state.output_bundle.section_notes
        if note.synthesis_status == SynthesisStatus.BLOCKED
    )

    print(f"Total sections: {final_state.total_sections}")
    print(f"Completed sections: {final_state.completed_sections}")
    print(f"Failed sections: {final_state.failed_sections}")
    print(f"READY sections: {ready_count}")
    print(f"PARTIAL sections: {partial_count}")
    print(f"BLOCKED sections: {blocked_count}")
    print(f"Execution time: {time.time() - start_time:.2f}s")


if __name__ == "__main__":
    main()
