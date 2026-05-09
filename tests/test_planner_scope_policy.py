from planner_agent.outline_prompt import build_chapter_outline_prompt
from planner_agent.schemas import (
    BookPlan,
    ChapterPlan,
    PlanningContext,
    SectionPlan,
    UserBookRequest,
)
from planner_agent.scope_builder import ScopeBuilder
from planner_agent.section_prompt import build_section_planner_prompt
from planner_agent.outline_schemas import ChapterOutlineItem
from planner_agent.validator import validate_book_plan


def _make_section(title: str) -> SectionPlan:
    return SectionPlan(
        title=title,
        goal=f"Teach {title.lower()} in a focused way.",
        key_questions=[f"What should the reader understand about {title.lower()}?"],
        estimated_words=700,
    )


def _make_chapter(
    number: int,
    title: str,
    goal: str,
    section_count: int = 4,
    project_milestone: str | None = None,
) -> ChapterPlan:
    return ChapterPlan(
        chapter_number=number,
        title=title,
        chapter_goal=goal,
        sections=[_make_section(f"{title} - Section {idx}") for idx in range(1, section_count + 1)],
        project_milestone=project_milestone,
    )


def test_user_book_request_normalizes_goals_constraints_and_infers_depth() -> None:
    payload = {
        "topic": "Retrieval-Augmented Generation for beginners",
        "audience": "software engineers new to GenAI",
        "tone": "practical and educational",
        "goals": [
            "explain what RAG is",
            "show why it matters",
            "explain the core architecture",
            "show a practical implementation view",
        ],
        "constraints": {
            "max_section_words": 900,
        },
    }

    request = UserBookRequest.model_validate(payload)

    assert request.depth == "introductory"
    assert request.max_section_words == 900
    assert request.constraints is not None
    assert request.constraints.max_section_words == 900
    assert request.normalized_goals == payload["goals"]
    assert request.is_focused_beginner_guide is True


def test_scope_builder_marks_beginner_practical_scope_as_focused() -> None:
    request = UserBookRequest.model_validate(
        {
            "topic": "Retrieval-Augmented Generation for beginners",
            "audience": "software engineers new to GenAI",
            "tone": "practical and educational",
            "goals": [
                "explain what RAG is",
                "show a practical implementation view",
            ],
        }
    )

    context = ScopeBuilder().build_context(request=request, discovery_bundle={})

    assert "simple working system" in context.book_purpose
    assert any("not a comprehensive handbook" in note.lower() for note in context.notes)
    assert any("advanced production" in item.lower() for item in context.scope_excludes)
    assert any("practical path" in item.lower() for item in context.scope_includes)


def test_outline_and_section_prompts_include_focused_guardrails() -> None:
    request = UserBookRequest.model_validate(
        {
            "topic": "Retrieval-Augmented Generation for beginners",
            "audience": "software engineers new to GenAI",
            "tone": "practical and educational",
            "goals": [
                "explain what RAG is",
                "show why it matters",
                "show a practical implementation view",
            ],
        }
    )
    context = PlanningContext(
        book_purpose="explain and help the reader build a simple working system",
        core_idea="A practical guide to understanding and building a simple RAG system.",
    )
    chapter = ChapterOutlineItem(
        chapter_number=3,
        title="Build a Simple RAG Pipeline",
        chapter_goal="Walk the reader through a first end-to-end implementation.",
    )

    outline_prompt = build_chapter_outline_prompt(request, context)
    section_prompt = build_section_planner_prompt(request, context, chapter)

    assert "focused beginner implementation guide" in outline_prompt
    assert "Target 5 to 7 chapters" in outline_prompt
    assert "Forbidden chapter families" in outline_prompt
    assert "Create 3 to 5 sections" in section_prompt
    assert "implementation-oriented" in section_prompt


def test_validator_rejects_overbroad_beginner_handbook_plan() -> None:
    request = UserBookRequest.model_validate(
        {
            "topic": "Retrieval-Augmented Generation for beginners",
            "audience": "software engineers new to GenAI",
            "tone": "practical and educational",
            "goals": [
                "explain what RAG is",
                "show why it matters",
                "show a practical implementation view",
            ],
            "constraints": {"max_section_words": 900},
        }
    )

    overbroad_plan = BookPlan(
        title="Retrieval-Augmented Generation for Software Engineers",
        audience=request.audience,
        tone=request.tone,
        depth=request.depth,
        running_project="Build a RAG chatbot",
        chapters=[
            _make_chapter(1, "Foundations of Large Language Models and Generative AI", "Cover broad LLM background.", project_milestone="Understand LLM basics"),
            _make_chapter(2, "What Is Retrieval-Augmented Generation?", "Explain the concept.", project_milestone="Understand RAG concept"),
            _make_chapter(3, "Evaluating RAG Systems", "Survey evaluation methods.", project_milestone="Know evaluation methods"),
            _make_chapter(4, "Scaling, Deployment, and Production Patterns", "Cover production operations.", project_milestone="Know production patterns"),
            _make_chapter(5, "Build a Simple RAG Pipeline", "Walk through a basic implementation.", project_milestone="Working pipeline"),
            _make_chapter(6, "Future Directions and Continuing Learning", "Survey future topics.", project_milestone="Know next steps"),
        ],
    )

    issues = validate_book_plan(overbroad_plan, request)

    assert any("excluded scope" in issue.lower() for issue in issues)
    assert any("practical payoff appears too late" in issue.lower() for issue in issues)


def test_validator_accepts_focused_beginner_practical_plan() -> None:
    request = UserBookRequest.model_validate(
        {
            "topic": "Retrieval-Augmented Generation for beginners",
            "audience": "software engineers new to GenAI",
            "tone": "practical and educational",
            "goals": [
                "explain what RAG is",
                "show why it matters",
                "explain the core architecture",
                "show a practical implementation view",
            ],
            "constraints": {"max_section_words": 900},
        }
    )

    focused_plan = BookPlan(
        title="Retrieval-Augmented Generation for Beginners",
        audience=request.audience,
        tone=request.tone,
        depth=request.depth,
        running_project="Build a simple RAG chatbot from scratch",
        chapters=[
            _make_chapter(1, "Why RAG Matters for Software Engineers", "Explain the problem RAG solves and why it matters.", project_milestone="Understand the problem RAG solves"),
            _make_chapter(2, "The Core Architecture of a Simple RAG System", "Introduce the retriever, index, and generator.", project_milestone="Understand retriever-generator architecture"),
            _make_chapter(3, "Build a Simple RAG Pipeline in Python", "Walk through a first implementation.", project_milestone="Working RAG pipeline"),
            _make_chapter(4, "Improve Retrieval Quality and Prompt Construction", "Show practical improvements and trade-offs.", project_milestone="Improved retrieval quality"),
            _make_chapter(5, "Debugging, Evaluation, and Common Mistakes", "Teach how to test and troubleshoot a simple system.", project_milestone="Tested and debugged system"),
        ],
    )

    issues = validate_book_plan(focused_plan, request)

    assert issues == []


def test_validator_allows_light_prototype_deployment_as_optional_next_step() -> None:
    request = UserBookRequest.model_validate(
        {
            "topic": "Retrieval-Augmented Generation for beginners",
            "audience": "software engineers new to GenAI",
            "tone": "practical and educational",
            "goals": [
                "explain what RAG is",
                "show why it matters",
                "explain the core architecture",
                "show a practical implementation view",
            ],
            "constraints": {"max_section_words": 900},
        }
    )

    focused_plan = BookPlan(
        title="Retrieval-Augmented Generation for Beginners",
        audience=request.audience,
        tone=request.tone,
        depth=request.depth,
        running_project="Build a simple RAG chatbot from scratch",
        chapters=[
            _make_chapter(1, "Why RAG Matters for Software Engineers", "Explain the problem RAG solves and why it matters.", project_milestone="Understand the problem RAG solves"),
            _make_chapter(2, "The Core Architecture of a Simple RAG System", "Introduce the retriever, index, and generator.", project_milestone="Understand retriever-generator architecture"),
            _make_chapter(3, "Build a Simple RAG Pipeline in Python", "Walk through a first implementation.", project_milestone="Working RAG pipeline"),
            _make_chapter(4, "Improve Retrieval Quality and Prompt Construction", "Show practical improvements and trade-offs.", project_milestone="Improved retrieval quality"),
            _make_chapter(5, "Debugging, Evaluation, and Common Mistakes", "Teach how to test and troubleshoot a simple system.", project_milestone="Tested and debugged system"),
            _make_chapter(
                6,
                "Next Steps: Extending and Lightly Deploying Your RAG Prototype",
                "Show a small set of safe beginner next steps after the first working prototype.",
                project_milestone="Extended prototype with deployment basics",
            ),
        ],
    )

    issues = validate_book_plan(focused_plan, request)

    assert issues == []
