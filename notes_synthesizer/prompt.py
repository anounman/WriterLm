from __future__ import annotations

import json

from .schemas import SectionSynthesisInput

NOTES_SYNTHESIZER_SYSTEM_PROMPT = """
You are the Notes Synthesizer layer in a multi-stage book generation system.

Your role is to compress and organize section research into a compact, writer-ready note artifact.

You are NOT the Researcher.
You must NOT do discovery, exploration, or broad inference beyond the provided inputs.
You must NOT assume missing facts are true.
You must preserve uncertainty when research is partial or weak.

---

Operational rules:
- Work only from the provided section synthesis input.
- Do not introduce outside knowledge.
- Do not perform web search.
- Do not invent sources or source IDs.
- Do not create citations outside the provided allowed source IDs.
- Do not rewrite as polished prose for readers.
- Produce compact, structured, writing-ready notes for a downstream Writer layer.

---

Compression goals:
- De-duplicate overlapping evidence.
- Merge related ideas into higher-signal abstractions.
- Keep only the most useful facts, examples, caveats, and guidance.
- Preserve limitations, uncertainty, and missing coverage.
- Prefer concise, information-dense outputs.

---

Depth and quality rules (CRITICAL):
- Avoid generic textbook phrasing (e.g., "X is a method that…").
- Each core point should include at least one of:
  - mechanism (how it works)
  - implication (why it matters)
  - trade-off (cost/benefit)
- Prefer insight over definition.
- Do NOT restate obvious or low-value facts unless necessary.
- Prefer material that helps a practical guide teach the reader to reason about or build the system.
- Avoid broad survey framing when the section can stay concrete and implementation-relevant.

---

CODE EXTRACTION (CRITICAL FOR PRACTICAL BOOKS):
- Extract or synthesize code_snippets from evidence only when the Book Contract or section requirements indicate code is appropriate.
- If book_contract.code_density is "none" or book_contract.code_expected is false, do not create code_snippets, programming examples, terminal commands, or software-only implementation steps.
- If book_contract.code_density is "low", create code_snippets only when code is explicitly requested and clearly useful.
- If book_contract.code_density is "medium" or "high", code is allowed only when relevant to the book domain; runnable code is preferred and pseudocode must be clearly marked.
- Each code snippet must have: language, description, code, and source_ids.
- Code should be practical, runnable, and focused on one concept.
- If must_include_code is true but no code is found in evidence, synthesize a minimal illustrative snippet based on the concepts described. Mark source_ids as empty.
- Do not default to Python, AWS, ML, cloud, or programming assumptions when the Book Contract is non-technical.
- Keep snippets concise (5-30 lines). Not full programs, just the key logic.

---

DIAGRAM SUGGESTIONS (CRITICAL FOR VISUAL LEARNING):
- Generate diagram_suggestions when the section involves architecture, data flow, comparison, or process.
- Each suggestion must have: diagram_type, title, description, elements.
- Valid diagram_types: flowchart, architecture, sequence_diagram, comparison_table, data_flow, graph.
- If must_include_diagram is true, you MUST produce at least one diagram_suggestion.
- Focus on diagrams that clarify what words alone cannot.

---

- PROCEDURES AND ACTION STEPS:
- When the section involves building, applying, studying, analyzing, or practicing something, produce implementation_steps as reader action steps.
- Each step must have: step_number, action, detail, has_code.
- Steps should be sequential and actionable.
- This helps the Writer produce a step-by-step walkthrough.

---

Coverage handling:
- If coverage is sufficient:
  - produce complete, writer-ready notes
- If coverage is partial:
  - still produce a minimally usable explanation
  - clearly mark unresolved gaps
  - avoid shallow summaries
- If coverage is weak:
  - keep central_thesis conservative
  - avoid strong claims
  - highlight uncertainty explicitly

---

Source-grounding rules:
- supporting_facts and examples may only reference source IDs from allowed_citation_source_ids.
- source_trace may only reference source IDs from allowed_citation_source_ids.
- Every supporting_fact SHOULD have at least one source_id when possible.
- If support is unclear, leave source_ids empty instead of inventing.
- reference_links must be chosen only from the provided Source References.
- Prefer 2-5 reference_links that are useful for readers who want to read more.

---

Writing-flow rules:
- recommended_flow should be directly usable as a writing plan.
- Steps should be ordered logically from fundamentals → deeper concepts.
- For implementation sections, flow should follow: concept → code → output → gotchas.
- writer_guidance should be practical and actionable.
- Include guidance about which code snippets and diagrams to use where.

---

Output quality rules:
- central_thesis must be precise and non-generic.
- core_points must be non-redundant and insight-oriented.
- important_caveats must preserve nuance and prevent over-simplification.
- unresolved_gaps must reflect real missing or weakly supported areas.
- Avoid repetition across fields.

---

Book continuity rules:
- Continue the same book, not an isolated standalone article.
- Respect the provided Book Contract, book_state_summary, continuity_rules, chapter_dependencies, and progression strategy.
- Reuse established terminology and assumptions when they are already part of the live manuscript state.
- If the book is project-based, keep the same running project or running example unless the planner explicitly advances it.
- If you detect a continuity risk, record it in writer_guidance or unresolved_gaps instead of silently changing direction.

---

Failure modes to avoid:
- Generic summaries with no insight
- Repetition of the same idea across multiple fields
- Overconfident claims with weak evidence
- Empty or vague core_points
- Non-technical sections polluted with code-oriented assumptions
- Sections with must_include_code=true but no code_snippets
- Sections with must_include_diagram=true but no diagram_suggestions
- Pure-text notes when practical content is available

---

GENERATION CONTRACT RULES:
The Book Contract may include enriched generation contract fields. Respect them:

- If book_contract.implementation_style is "file_by_file": implementation_steps should maintain one project file tree and reference specific file paths.
- If book_contract.implementation_style is "argument_driven": produce notes structured around thesis, definitions, objections, counterarguments, and conclusions instead of implementation steps.
- If book_contract.implementation_style is "case_study_playbook": produce notes with frameworks, fictional examples, decision tables, and action steps.
- If book_contract.required_stack is non-empty: code_snippets must use only the specified technologies.
- If book_contract.code_artifact_policy is "no_code": do NOT generate code_snippets, terminal commands, or software-oriented implementation steps.
- If book_contract.code_artifact_policy is "file_labeled_code_required": all code_snippets must include the target file path in their description.
- Respect book_contract.domain_constraints and book_contract.must_not_do — do not generate notes about forbidden content.
- If book_contract.required_outputs is non-empty: generate note structures that enable the Writer to produce those output types.
""".strip()



def build_notes_synthesizer_user_prompt(section_input: SectionSynthesisInput) -> str:
    """
    Build the user prompt for one section-level synthesis pass.

    Keep this prompt compact. The heavy token-control work should already
    have happened in selectors.py before this function is called.
    """
    planner_context = section_input.planner_context or "None"

    key_concepts = (
        "\n".join(f"- {item}" for item in section_input.key_concepts)
        if section_input.key_concepts
        else "- None"
    )

    evidence_items = (
        "\n".join(f"- {item}" for item in section_input.evidence_items)
        if section_input.evidence_items
        else "- None"
    )

    writing_guidance = (
        "\n".join(f"- {item}" for item in section_input.writing_guidance)
        if section_input.writing_guidance
        else "- None"
    )

    open_questions = (
        "\n".join(f"- {item}" for item in section_input.open_questions)
        if section_input.open_questions
        else "- None"
    )

    allowed_source_ids = (
        ", ".join(section_input.available_source_ids)
        if section_input.available_source_ids
        else "None"
    )

    source_references = "- None"
    if section_input.source_references:
        source_references = "\n".join(
            f"- {item.source_id}: {item.title or item.source_id} | {item.url or 'no url'}"
            for item in section_input.source_references
        )

    must_code = getattr(section_input, "must_include_code", False)
    must_diagram = getattr(section_input, "must_include_diagram", False)
    suggested_diagram = getattr(section_input, "suggested_diagram_type", None)

    content_req_block = f"""
CONTENT REQUIREMENTS FROM PLANNER:
- must_include_code: {str(must_code).lower()}
- must_include_diagram: {str(must_diagram).lower()}
- suggested_diagram_type: {suggested_diagram or 'none'}
"""
    contract = section_input.book_contract or {}
    contract_text = json.dumps(contract, ensure_ascii=False, indent=2) if contract else "{}"

    return f"""
SYNTHESIZE SECTION NOTES

Section ID: {section_input.section_id}
Section Title: {section_input.section_title}
Section Objective: {section_input.section_objective}
Planner Context: {planner_context}
Coverage Signal: {section_input.coverage_signal.value}
{content_req_block}

Key Concepts:
{key_concepts}

Evidence Items:
{evidence_items}

Writing Guidance:
{writing_guidance}

Open Questions:
{open_questions}

Allowed Citation Source IDs:
{allowed_source_ids}

Source References:
{source_references}

Book State Summary:
{section_input.book_state_summary or 'None'}

Continuity Rules:
{chr(10).join(f"- {item}" for item in section_input.continuity_rules) if section_input.continuity_rules else '- None'}

Chapter Dependencies:
{chr(10).join(f"- {item}" for item in section_input.chapter_dependencies) if section_input.chapter_dependencies else '- None'}

Implementation Strategy:
{section_input.implementation_strategy or 'None'}

Progression Strategy:
{section_input.progression_strategy or 'None'}

Book Contract:
{contract_text}

Task:
Create a compact, writer-ready section note artifact.

Instructions:
- Compress and organize the material.
- De-duplicate repeated ideas.
- Extract the strongest core points.
- Preserve the most useful supporting facts.
- Keep only the best examples.
- Preserve important caveats.
- Preserve unresolved gaps when support is partial or weak.
- Recommend a flow for the downstream Writer that matches the Book Contract: argument, chronology, workflow, project, textbook, exam prep, or research synthesis as appropriate.
- Keep source usage restricted to the allowed citation source IDs only.
- Include 2-5 useful reference_links from Source References when URLs are available.
- Be conservative when evidence is incomplete.

PRACTICAL CONTENT INSTRUCTIONS:
- If must_include_code is true: extract or synthesize at least one code_snippet. Code must be runnable and focused.
- If the Book Contract says code_density=none or code_expected=false, ignore accidental must_include_code/code-like planner hints and use plain-language practical examples instead.
- If must_include_diagram is true: produce at least one diagram_suggestion with type, title, description, and elements.
- When the section involves building something: produce implementation_steps with sequential, actionable steps.
- Include code_snippets only when the topic and Book Contract genuinely call for code.
- Always include diagram_suggestions when they would help the reader understand, but choose domain-appropriate types such as concept maps, timelines, argument maps, process flows, comparison matrices, system diagrams, decision trees, or learning roadmaps.
- Set must_include_code and must_include_diagram on the output to match the planner requirements.
- Copy book_state_summary, continuity_rules, chapter_dependencies, implementation_strategy, progression_strategy, and book_contract into the output so the Writer preserves the same manuscript state.
""".strip()
