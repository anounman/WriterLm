from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, List

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

from writer.graph import build_writer_graph, initialize_writer_state
from writer.llm import GroqStructuredLLM
from writer.schemas import WritingStatus, WriterSectionInput
from writer.state import WriterInput, WriterSectionTask, WriterState
from llm_provider import (
    get_default_models_for_layer,
    get_legacy_model_env_names_by_provider,
    resolve_openai_compatible_config,
)


INPUT_PATH = REPO_ROOT / "outputs" / "notes_bundle.json"
OUTPUT_PATH = REPO_ROOT / "outputs" / "writer_bundle.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Notes bundle not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_tasks_from_notes_bundle(bundle: dict[str, Any]) -> List[WriterSectionTask]:
    tasks: List[WriterSectionTask] = []

    section_notes = bundle.get("section_notes")
    if not isinstance(section_notes, list):
        return tasks

    for note in section_notes:
        if not isinstance(note, dict):
            continue

        try:
            section_input = WriterSectionInput(
                section_id=note.get("section_id"),
                section_title=note.get("section_title"),
                synthesis_status=note.get("synthesis_status"),
                central_thesis=note.get("central_thesis"),
                core_points=note.get("core_points") or [],
                supporting_facts=note.get("supporting_facts") or [],
                examples=note.get("examples") or [],
                code_snippets=note.get("code_snippets") or [],
                diagram_suggestions=note.get("diagram_suggestions") or [],
                implementation_steps=note.get("implementation_steps") or [],
                must_include_code=note.get("must_include_code", False),
                must_include_diagram=note.get("must_include_diagram", False),
                important_caveats=note.get("important_caveats") or [],
                unresolved_gaps=note.get("unresolved_gaps") or [],
                recommended_flow=note.get("recommended_flow") or [],
                writer_guidance=note.get("writer_guidance") or [],
                allowed_citation_source_ids=note.get("allowed_citation_source_ids") or [],
                reference_links=note.get("reference_links") or [],
                book_state_summary=note.get("book_state_summary") or "",
                continuity_rules=note.get("continuity_rules") or [],
                chapter_dependencies=note.get("chapter_dependencies") or [],
                implementation_strategy=note.get("implementation_strategy"),
                progression_strategy=note.get("progression_strategy"),
                book_contract=note.get("book_contract") or {},
            )

            task = WriterSectionTask(
                section_id=section_input.section_id,
                section_title=section_input.section_title,
                section_input=section_input,
            )

            tasks.append(task)

        except Exception:
            continue

    return tasks


def save_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def main() -> None:
    start_time = time.time()

    bundle = load_json(INPUT_PATH)
    tasks = build_tasks_from_notes_bundle(bundle)

    if not tasks:
        print("No Writer tasks created.")
        raise SystemExit(1)

    llm_config = resolve_openai_compatible_config(
        layer="writer",
        default_models=get_default_models_for_layer("writer"),
        legacy_env_names_by_provider=get_legacy_model_env_names_by_provider(),
    )
    llm = GroqStructuredLLM(
        api_key=llm_config.api_key,
        model=llm_config.model,
        base_url=llm_config.base_url,
    )

    input_data = WriterInput(
        book_id="test_run",
        book_title="Test Book",
        tasks=tasks,
    )

    graph = build_writer_graph(llm)
    state = initialize_writer_state(input_data)
    final_state_raw = graph.invoke(state)
    final_state = WriterState.model_validate(final_state_raw)

    if final_state.output_bundle is None:
        raise RuntimeError("Writer completed without output bundle.")

    save_output(
        OUTPUT_PATH,
        final_state.output_bundle.model_dump(mode="json"),
    )

    ready = sum(
        1 for d in final_state.output_bundle.section_drafts
        if d.writing_status == WritingStatus.READY
    )
    partial = sum(
        1 for d in final_state.output_bundle.section_drafts
        if d.writing_status == WritingStatus.PARTIAL
    )
    blocked = sum(
        1 for d in final_state.output_bundle.section_drafts
        if d.writing_status == WritingStatus.BLOCKED
    )

    print(f"Total sections: {final_state.total_sections}")
    print(f"Completed sections: {final_state.completed_sections}")
    print(f"Failed sections: {final_state.failed_sections}")
    print(f"READY sections: {ready}")
    print(f"PARTIAL sections: {partial}")
    print(f"BLOCKED sections: {blocked}")
    print(f"Execution time: {time.time() - start_time:.2f}s")


if __name__ == "__main__":
    main()
