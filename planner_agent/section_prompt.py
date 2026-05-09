import json

from planner_agent.outline_schemas import ChapterOutlineItem
from planner_agent.schemas import PlanningContext, UserBookRequest


SECTION_PLANNER_SYSTEM_PROMPT = """
You are a section-planning engine.

Your task is to expand exactly one chapter into a clean section plan.

STRICT OUTPUT RULES:
- Return ONLY valid JSON.
- Do NOT return markdown.
- Do NOT wrap the JSON in code fences.
- Do NOT add explanations, notes, or extra text.
- Do NOT return a partial answer.
- The JSON must be complete and parseable.

PLANNING RULES:
- Expand exactly one chapter.
- Each section must focus on one clear idea.
- Avoid overlap and repetition between sections.
- Keep section titles specific, concrete, and bounded.
- Keep sections teachable and writable in one pass.
- estimated_words should usually stay between 200 and 1200.
- Each section must have a clear teaching goal.
- Each section must include key questions that guide later writing.

CONTENT REQUIREMENTS (CRITICAL):
- Every section MUST specify content_requirements with:
  - must_include_code: true/false — whether the section needs programming/code examples
  - must_include_example: true/false — whether the section needs a concrete example, worked problem, analogy, or case
  - must_include_diagram: true/false — whether the section needs a diagram or visualization
  - suggested_diagram_type: null or a string like "flowchart", "architecture", "comparison_table", "sequence_diagram", "data_flow"
- For implementation-oriented software chapters: MOST sections should have must_include_code = true.
- For non-software chapters: do not add code unless the topic explicitly requires programming, commands, formulas-as-code, or computational examples.
- For math/course/theory chapters: use worked examples, concept maps, tables, diagrams, or visual intuition; do not add code unless explicitly useful.
- For philosophy/history/psychology/business chapters: prefer argument maps, timelines, evidence maps, process flows, decision trees, examples, cases, or comparison matrices as appropriate.
- For conceptual sections: must_include_example should be true and consider must_include_diagram = true.
- NO section should have ALL three set to false. Every section must include at least one of: code, example, or diagram.

PROJECT CONTINUITY:
- If the chapter has a project_milestone, sections should build toward it progressively.
- Use the builds_on field to link sections that depend on previous ones (reference the previous section title).
- The last section in an implementation chapter should integrate what was built in prior sections.

FOCUSED-BEGINNER RULES:
- When the request is a focused beginner practical guide, do NOT inflate the chapter into a mini-handbook.
- Prefer sections that help the reader understand or build something.
- Avoid survey-completion sections whose purpose is merely to cover more territory.
- If the chapter is implementation-oriented, include concrete build/debug/use sections instead of abstract thematic buckets.

IMPORTANT:
- Do NOT create other chapters.
- Do NOT redesign the whole book.
- Do NOT add subsections yet.
- Only expand the given chapter into sections.
""".strip()


def build_section_planner_prompt(
    request: UserBookRequest,
    context: PlanningContext,
    chapter: ChapterOutlineItem,
) -> str:
    schema_hint = {
        "chapter_number": 1,
        "chapter_title": "string",
        "chapter_goal": "string",
        "project_milestone": "string or null",
        "sections": [
            {
                "title": "string",
                "goal": "string",
                "key_questions": ["string"],
                "estimated_words": 500,
                "content_requirements": {
                    "must_include_code": True,
                    "must_include_example": True,
                    "must_include_diagram": False,
                    "suggested_diagram_type": "null or string",
                },
                "builds_on": "null or title of previous section",
            }
        ],
    }

    min_sections, max_sections = request.preferred_sections_per_chapter_range
    max_section_words_instruction = (
        f"- No section may exceed {request.max_section_words} estimated words."
        if request.max_section_words is not None
        else "- Choose appropriate estimated_words for each section, usually between 200 and 1200."
    )

    chapter_text = f"{chapter.title} {chapter.chapter_goal}".lower()
    chapter_is_implementation_oriented = (
        request.effective_book_type == "implementation_guide"
        or request.project_based
        or any(
        signal in chapter_text
        for signal in (
            "build",
            "implement",
            "implementation",
            "pipeline",
            "walkthrough",
            "tutorial",
            "debug",
            "prototype",
            "hands-on",
            "code",
        )
        )
    )

    chapter_is_software_or_code = request.content_density.code_density != "low" or any(
        signal in f"{request.topic} {chapter_text}".lower()
        for signal in ("code", "python", "api", "software", "program", "app", "pipeline")
    )

    if chapter_is_implementation_oriented and chapter_is_software_or_code:
        implementation_guidance = (
        "- This chapter is implementation-oriented. Make sections concrete and sequential, such as setup, architecture, build steps, debugging, and improvement.\n"
        "- MOST sections in this chapter MUST have must_include_code = true.\n"
        "- At least one section should have a useful structured visual when it clarifies architecture, process, dependency, or validation."
        )
    elif request.effective_book_type in {"textbook", "course_companion", "practice_workbook", "exam_prep"}:
        implementation_guidance = (
            "- This is a textbook/course/practice chapter. Make sections progress through theory, worked examples, and practice.\n"
            "- Prefer must_include_example = true for worked problems or concrete examples.\n"
            "- Set must_include_code = true only if the topic explicitly requires programming.\n"
        "- Use diagrams/tables for conceptual maps, graphs, timelines, argument maps, tables, geometry, or visual intuition where useful."
        )
    else:
        implementation_guidance = (
        "- Keep sections concrete and directly useful to the stated chapter goal.\n"
        "- Conceptual sections should usually have must_include_example = true.\n"
        "- Use must_include_diagram = true only when a structured visual would add value."
        )

    content_density = request.content_density
    density_guidance = f"""
CONTENT DENSITY TARGETS:
- Code density: {content_density.code_density} — {"set must_include_code = true for every section only for programming/software content" if content_density.code_density == "high" else "set must_include_code = true for most implementation sections only when the topic requires code" if content_density.code_density == "medium" else "set must_include_code = true only where essential"}
- Example density: {content_density.example_density} — {"set must_include_example = true for every section" if content_density.example_density == "high" else "set must_include_example = true for most sections" if content_density.example_density == "medium" else "set must_include_example = true where helpful"}
- Diagram density: {content_density.diagram_density} — {"set must_include_diagram = true wherever structured visuals add clear value" if content_density.diagram_density == "high" else "set must_include_diagram = true for the highest-value visual moments, not as filler" if content_density.diagram_density == "medium" else "set must_include_diagram = true for key concept sections only"}
- HARD RULE: No section may have ALL three (must_include_code, must_include_example, must_include_diagram) set to false.
"""

    project_milestone_text = ""
    if hasattr(chapter, "project_milestone") and chapter.project_milestone:
        project_milestone_text = f"\nChapter project milestone: {chapter.project_milestone}"

    return f"""
Expand exactly one chapter into a section plan.

USER INPUT
Topic: {request.topic}
Audience: {request.audience}
Tone: {request.tone}
Depth: {request.depth}
Book type: {request.book_type} (effective: {request.effective_book_type})
Theory/practice balance: {request.theory_practice_balance} (effective: {request.effective_theory_practice_balance})
Pedagogy style: {request.pedagogy_style}
Goals:
{json.dumps(request.normalized_goals, indent=2)}

REQUEST PROFILE
Project-based: {str(request.project_based).lower()}
Focused beginner practical guide: {str(request.is_focused_beginner_guide).lower()}
Practical focus: {str(request.is_practical_focused).lower()}

UPLOADED SOURCE CONTEXT:
{json.dumps(request.source_context.model_dump(mode="json") if request.source_context else {}, indent=2)}

PLANNING CONTEXT
Book purpose: {context.book_purpose}
Core idea: {context.core_idea}

Audience needs:
{json.dumps(context.audience_needs, indent=2)}

Main questions the book should answer:
{json.dumps(context.main_questions, indent=2)}

Scope should include:
{json.dumps(context.scope_includes, indent=2)}

Scope should exclude:
{json.dumps(context.scope_excludes, indent=2)}

Key themes:
{json.dumps(context.key_themes, indent=2)}

Sequence logic:
{json.dumps(context.sequence_logic, indent=2)}

CHAPTER TO EXPAND
Chapter number: {chapter.chapter_number}
Chapter title: {chapter.title}
Chapter goal: {chapter.chapter_goal}{project_milestone_text}
{density_guidance}

IMPORTANT CONSTRAINTS:
{max_section_words_instruction}
- Create {min_sections} to {max_sections} sections for this chapter.
- Each section must support the chapter goal.
- Each section must focus on one clear idea only.
- Avoid vague titles unless they are tightly scoped.
- Avoid repetition and avoid sections that exist only to broaden coverage.
- Keep the order pedagogical and easy to follow.
{implementation_guidance}
- For uploaded exercise sheets, create sections that teach the underlying method and include original source-inspired worked examples or practice prompts.
- Every section must have title, goal, key_questions, estimated_words, and content_requirements.
- Use builds_on to chain sections that form a progressive build sequence, argument sequence, chronology, workflow, or learning scaffold.
- Return only this chapter's section plan.
- Do not create sections for any other chapter.

Before finalizing, silently check:
1. The JSON is complete.
2. The output expands exactly this chapter.
3. There are {min_sections} to {max_sections} sections.
4. Every section has title, goal, key_questions, estimated_words, and content_requirements.
5. No section has all content_requirements set to false.
6. The sections support the chapter goal without drifting into excluded scope.
7. The response contains only JSON.
8. The sections are concrete enough for the requested book type.

Return ONLY JSON in this exact structure:
{json.dumps(schema_hint, indent=2)}
""".strip()
