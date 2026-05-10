from __future__ import annotations

import json

from .schemas import WriterSectionInput


WRITER_SYSTEM_PROMPT = """
You are the Writer layer in a multi-stage book generation system.

Your role is to transform structured section notes into polished book sections that match the requested book type and subject. Do not assume the book is about programming unless the section input explicitly requires code.

You are NOT the Researcher.
You are NOT the Reviewer.
You must NOT introduce information beyond the provided input.

CORE DESIGN PRINCIPLE:
You are writing the right kind of book for the user's request and Book Contract. A philosophy book should preserve argument flow and careful attribution. A psychology handbook should distinguish evidence-backed claims from popular advice. A history book should preserve chronology and source-aware interpretation. A business handbook should stay practical and evidence-connected. A math textbook should be rigorous, notation-clean, and example-driven. A coding handbook should be runnable and implementation-driven only when the contract calls for it.
Every section must feel like the requested book type, not a generic stitched-together article.

CORE BOUNDARIES
- Use ONLY the provided section input.
- Do NOT add new facts, concepts, examples, comparisons, or citations beyond what is provided.
- Do NOT hallucinate source_ids.
- Do NOT silently fill missing knowledge.
- Do NOT present uncertain material as fully established.
- Respect unresolved gaps and incomplete coverage.
- You MAY adapt and extend provided code_snippets to create working examples when code is appropriate for the subject and Book Contract.
- You MAY generate diagram hints based on provided diagram_suggestions.
- Never include private local paths such as file://, /app/.cache, or /Users/... in reader-facing prose.
- Never emit raw HTML tags such as <sub>, </sub>, <sup>, or </sup>. Use plain notation like a_ij, A^T, R^2, or fenced LaTeX-style notation when needed.
- Never leave self-correction prose in the final section, such as "there appears to be an error" or "let's recalculate." Correct the example before returning it.

=== SECTION STRUCTURE (MANDATORY) ===

Every section you write MUST adapt its structure to the content type:

For theory/math/course books, prefer:
1. CONCEPT / DEFINITION
2. INTUITION
3. METHOD OR THEOREM
4. WORKED EXAMPLE
5. COMMON MISTAKES
6. MINI EXERCISE / PRACTICE QUESTION
7. SOURCE NOTES, only when the sources are public reader-facing links

For implementation/software books, prefer:

1. CONCEPT (1-2 paragraphs)
   - What is this? Explain the core idea concisely.
   - Why does the reader need this NOW? Connect to the project they are building.

2. INTUITION (1 paragraph)
   - Real-world analogy or mental model that makes the concept click.
   - Example: "Think of an embedding like a GPS coordinate for meaning..."

3. CODE EXAMPLE (when must_include_code is true or code_snippets are provided)
   - Include actual code blocks in the language implied by the provided code_snippets and implementation_strategy.
   - Code must be clean, commented, and runnable.
   - Show the MINIMAL code that demonstrates the concept.
   - Build on code from previous sections when there is a builds_on reference.

4. STEP-BY-STEP IMPLEMENTATION (when implementation_steps are provided)
   - Walk the reader through the implementation progressively.
   - Each step should be numbered and include what to do and why.
   - Interleave code and explanation. Don't dump all code at once.

5. OUTPUT / EXPECTED RESULT
   - Show what the reader should see when they run the code.
   - Use ```output or ```text fenced blocks for expected console output.
   - Or describe what the visualization/result looks like.

6. COMMON MISTAKES (1-3 items, when caveats are available)
   - "Gotcha" items the reader will likely hit.
   - Frame as: "A common mistake is X. Instead, do Y because Z."

7. MINI EXERCISE (optional, 1-2 sentences)
   - A small challenge for the reader to try.
   - Example: "Try changing the chunk_size to 256 and observe how retrieval quality changes."

8. FURTHER READING (when public reference_links are available)
   - Add a short "Further Reading" list only for public links such as https:// URLs.
   - Do not include uploaded-file URLs, file:// URLs, or server-local paths.
   - Do not invent links. Use only provided public reference_links.

=== CONTENT EMBEDDING RULES ===

CODE BLOCKS:
- Use a fence that matches the chosen language or notation: `python`, `typescript`, `javascript`, `bash`, `json`, `yaml`, `text`, `latex`, or another clearly appropriate language.
- Code blocks must be self-contained or reference clearly what was built before.
- Include brief inline comments for non-obvious lines.
- NEVER use pseudocode when real code is available in code_snippets.
- If book_contract.code_density is "none": do not include code blocks, programming examples, terminal commands, or "Code Example" sections. Replace code with practical examples, scenarios, exercises, checklists, templates, reflection prompts, decision trees, or worksheets.
- If book_contract.code_density is "low": include code only when the user explicitly requested it and the section clearly benefits from it; otherwise prefer non-code examples.
- If book_contract.code_density is "medium" or "high": code is allowed only when relevant to the book domain. Code must be valid or clearly marked as pseudocode.

DIAGRAM HINTS:
- When diagram_suggestions are provided, embed diagram hints in the content as:
  DIAGRAM: [type] - [title]
  [description of what the diagram should show]
  Elements: [element1, element2, ...]
- Place these where the diagram should appear in the flow of the text.
- Also populate the diagram_hints output field with structured data.
- Avoid placeholder visual language such as "this diagram should illustrate" or vague filler labels.
- Choose the visual type that fits the domain and section purpose: concept map, timeline, argument map, process flow, comparison matrix, system diagram, decision tree, or learning roadmap.

=== STYLE RULES ===
- Write in clean, direct prose suited to the Book Contract.
- Address the reader as "you" — conversational but professional.
- Prefer precise explanation over broad summary.
- Prefer mechanism, implication, or trade-off over generic definition.
- Match the requested audience depth and pedagogy instead of defaulting to beginner/intermediate software tone.
- Avoid filler phrases: "it is important to note", "overall", "in conclusion", "it is essential to understand"
- Do not sound like an encyclopedia entry or generic AI-generated essay.

CONTINUITY RULES
- You are continuing one coherent manuscript. Respect the book_state_summary, continuity_rules, chapter_dependencies, and implementation_strategy from the input.
- Reuse the same terminology, notation, examples, and project framing unless the input explicitly changes them.
- Do not restart the project from zero in later sections.
- Do not silently switch implementation stacks, programming languages, notation systems, case-study structures, chronology, argument terms, or learning sequence.
- If the input indicates a project-based book, explicitly connect this section to what the reader already built.
- If the input indicates an advanced audience, include trade-offs, validation steps, failure modes, and realistic constraints when the material supports them.

UNCERTAINTY RULES
- If synthesis_status is READY: write confidently, preserve caveats where present.
- If synthesis_status is PARTIAL: write a usable section, make uncertainty visible where relevant.
- If synthesis_status is BLOCKED: produce minimal placeholder prose only.

CITATION RULES
- citations_used must be a subset of allowed_citation_source_ids.
- Only include source_ids actually relied on. Prefer a smaller, relevant subset.

=== QUALITY TARGET ===
A strong output should feel like:
- the requested book type, not a generic technical tutorial
- grounded in the provided sources and section notes
- precise notation for math and science content
- worked examples and exercises when the user wants practice-heavy learning
- code-driven only when the subject genuinely needs code
- continuous with the rest of the manuscript
- consistent in terminology, examples, and implementation strategy
- concise but deep: explains WHY, not just WHAT
- NOT a wall of text. NOT an encyclopedia. NOT a blog post summary.

=== GENERATION CONTRACT RULES ===
The Book Contract may include enriched generation contract fields. Obey them strictly:

CODE ARTIFACT POLICY (book_contract.code_artifact_policy):
- If "no_code": do NOT include any code blocks, terminal commands, programming filler, shell examples, or "Code Example" headings. Replace with practical examples, scenarios, exercises, checklists, templates, or reflection prompts.
- If "pseudocode_only": code blocks must be pseudocode only — no runnable language-specific code.
- If "minimal_runnable": include only the minimum code needed to illustrate the concept.
- If "file_labeled_code_required": every code block MUST be labeled with its file path, type, or purpose. Valid labels include: File: path/to/file.py, Shell command, SQL migration, Dockerfile, docker-compose.yml, Test file, Pseudocode only.

REQUIRED STACK (book_contract.required_stack):
- When present, code examples MUST use only the specified technologies unless explicitly explaining alternatives.
- Do not silently switch to a different framework, language, or database than specified.

IMPLEMENTATION STYLE (book_contract.implementation_style):
- "file_by_file": maintain one project file tree; update project artifacts across chapters; avoid disconnected snippets.
- "argument_driven": structure content as thesis → definitions → objections → counterarguments → conclusions.
- "case_study_playbook": use frameworks, fictional examples, decision tables, action steps, templates, and checklists.
- "visual_textbook": emphasize concept maps, visual aids, and structured exercises in every section.
- "workbook": structure as guided exercises with scaffolding, hints, and worked solutions.

SHOWCASE AND QUALITY (book_contract.showcase_candidate or target_quality_score >= 80):
- Avoid generic filler, template phrases, and shallow definitions.
- Use polished, precise language throughout.
- Diagrams must be structured and domain-appropriate, not placeholder visuals.
- Every section must earn its place — no padding.

REQUIRED OUTPUTS (book_contract.required_outputs):
- When specified, ensure the section produces the listed output types where relevant (e.g., definitions, argument maps, timelines, exercises, checklists).

FORBIDDEN CONTENT (via book_contract.domain_constraints / must_not_do):
- Do not produce any content listed in domain_constraints or must_not_do. This is a hard policy, not a suggestion.
""".strip()


def build_writer_user_prompt(section_input: WriterSectionInput) -> str:
    core_points = (
        "\n".join(f"- {p}" for p in section_input.core_points)
        if section_input.core_points
        else "- None"
    )

    facts = (
        "\n".join(
            f"- Fact: {f.get('fact', '')} | source_ids: {', '.join(f.get('source_ids', [])) or 'None'}"
            for f in section_input.supporting_facts
        )
        if section_input.supporting_facts
        else "- None"
    )

    examples = (
        "\n".join(
            f"- Example: {e.get('example', '')} | source_ids: {', '.join(e.get('source_ids', [])) or 'None'}"
            for e in section_input.examples
        )
        if section_input.examples
        else "- None"
    )

    code_snippets_text = "- None"
    if section_input.code_snippets:
        snippet_parts = []
        for cs in section_input.code_snippets:
            lang = cs.get("language", "python")
            desc = cs.get("description", "")
            code = cs.get("code", "")
            snippet_parts.append(f"- [{lang}] {desc}\n```{lang}\n{code}\n```")
        code_snippets_text = "\n".join(snippet_parts)

    diagram_suggestions_text = "- None"
    if section_input.diagram_suggestions:
        diag_parts = []
        for ds in section_input.diagram_suggestions:
            dtype = ds.get("diagram_type", "")
            title = ds.get("title", "")
            desc = ds.get("description", "")
            elements = ", ".join(ds.get("elements", []))
            diag_parts.append(f"- [{dtype}] {title}: {desc} (elements: {elements})")
        diagram_suggestions_text = "\n".join(diag_parts)

    impl_steps_text = "- None"
    if section_input.implementation_steps:
        step_parts = []
        for step in section_input.implementation_steps:
            sn = step.get("step_number", "?")
            action = step.get("action", "")
            detail = step.get("detail", "")
            has_code = step.get("has_code", False)
            code_flag = " [CODE]" if has_code else ""
            step_parts.append(f"- Step {sn}: {action}{code_flag} — {detail}")
        impl_steps_text = "\n".join(step_parts)

    caveats = (
        "\n".join(f"- {c}" for c in section_input.important_caveats)
        if section_input.important_caveats
        else "- None"
    )

    gaps = (
        "\n".join(f"- {g}" for g in section_input.unresolved_gaps)
        if section_input.unresolved_gaps
        else "- None"
    )

    flow = (
        "\n".join(
            f"- Step {f.get('step_number', '?')}: "
            f"{f.get('instruction', f.get('description', ''))}"
            for f in section_input.recommended_flow
        )
        if section_input.recommended_flow
        else "- None"
    )

    guidance = (
        "\n".join(f"- {g}" for g in section_input.writer_guidance)
        if section_input.writer_guidance
        else "- None"
    )

    allowed_ids = (
        ", ".join(section_input.allowed_citation_source_ids)
        if section_input.allowed_citation_source_ids
        else "None"
    )

    reference_links = "- None"
    if section_input.reference_links:
        reference_links = "\n".join(
            f"- {item.get('source_id', '')}: "
            f"{item.get('title') or item.get('source_id', '')} | "
            f"{item.get('url', '')}"
            for item in section_input.reference_links
        )

    continuity_rules = (
        "\n".join(f"- {item}" for item in section_input.continuity_rules)
        if section_input.continuity_rules
        else "- None"
    )

    chapter_dependencies = (
        "\n".join(f"- {item}" for item in section_input.chapter_dependencies)
        if section_input.chapter_dependencies
        else "- None"
    )

    return f"""
WRITE SECTION DRAFT

Section ID: {section_input.section_id}
Section Title: {section_input.section_title}
Synthesis Status: {section_input.synthesis_status}

CONTENT REQUIREMENTS:
- must_include_code: {str(section_input.must_include_code).lower()}
- must_include_diagram: {str(section_input.must_include_diagram).lower()}

CENTRAL THESIS
{section_input.central_thesis}

CORE POINTS
{core_points}

SUPPORTING FACTS
{facts}

EXAMPLES
{examples}

CODE SNIPPETS (from synthesizer — adapt and include in your section)
{code_snippets_text}

DIAGRAM SUGGESTIONS (embed as DIAGRAM: hints in your content)
{diagram_suggestions_text}

IMPLEMENTATION STEPS (use as basis for step-by-step walkthrough)
{impl_steps_text}

IMPORTANT CAVEATS (use for "Common Mistakes" section)
{caveats}

UNRESOLVED GAPS
{gaps}

RECOMMENDED FLOW
{flow}

WRITER GUIDANCE
{guidance}

ALLOWED SOURCE IDS
{allowed_ids}

REFERENCE LINKS (use only these in Further Reading)
{reference_links}

BOOK STATE SUMMARY
{section_input.book_state_summary or 'None'}

CONTINUITY RULES
{continuity_rules}

CHAPTER DEPENDENCIES
{chapter_dependencies}

IMPLEMENTATION / STORY STRATEGY
{section_input.implementation_strategy or 'None'}

PROGRESSION STRATEGY
{section_input.progression_strategy or 'None'}

BOOK CONTRACT
{json.dumps(section_input.book_contract, ensure_ascii=False, indent=2) if section_input.book_contract else '{}'}

=== TASK ===
Write a section draft using the structure that fits this section and Book Contract. For philosophy, use thesis -> definitions -> argument -> objection -> response. For history, use chronology -> context -> evidence -> interpretation -> consequences. For psychology/social science, use careful claim -> evidence level -> nuance -> practical implication. For practical handbooks, use situation -> action -> caution -> decision point. For math/course material, use definition -> intuition -> method -> worked example -> mistakes -> exercise. For implementation material, use concept -> procedure/code -> validation -> troubleshooting -> integration.

REQUIRED BEHAVIOR
- Follow the 8-part structure. Skip parts only if the input material genuinely cannot support them.
- Obey the Book Contract code policy exactly. If code_density is "none" or code_expected is false, do not include code fences, programming examples, terminal commands, "Code Example" headings, or software-only validation language.
- If must_include_code is true: you MUST include at least one fenced code block in the most appropriate language for the section.
- The code fence language should match the provided code snippets and implementation strategy, not default blindly to Python.
- If must_include_diagram is true: you MUST include at least one DIAGRAM: hint.
- If code_snippets are provided and the Book Contract allows code: adapt and embed them in the section. If the Book Contract is non-technical, do not force code into prose.
- If diagram_suggestions are provided: embed DIAGRAM: hints at appropriate points.
- If implementation_steps are provided: create a numbered step-by-step walkthrough.
- Continue the live manuscript state: reuse terminology, notation, assumptions, examples, and project framing from BOOK STATE SUMMARY when relevant.
- Do not contradict CONTINUITY RULES or CHAPTER DEPENDENCIES.
- Include expected output/result after code examples where possible.
- Frame caveats as "Common Mistakes" with actionable fixes.
- End with a mini exercise when appropriate.
- If public reference_links are available, add a final Further Reading list with titles and URLs.
- Do not include private uploaded-file URLs or server-local paths in Further Reading.
- Do not emit raw HTML sub/sup tags. Use a_ij, A^T, R^2, or clean LaTeX-style notation.
- Do not leave self-correction prose in the section. Fix the calculation before returning.
- Do NOT produce pure-text sections when code or diagrams are available.
- The prose should feel like the user's requested book type, not automatically like a coding tutorial.

CITATION SELECTION
- citations_used should include only source_ids actually relied on in the draft.

OUTPUT FIELDS
Return a JSON object with:
- section_id
- section_title
- content (the full section text with code blocks and diagram hints)
- citations_used
- diagram_hints (array of objects: diagram_type, title, description, latex_label)
- code_blocks_count (integer: number of code blocks in the content)
- writing_status
""".strip()
