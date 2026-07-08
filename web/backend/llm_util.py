import json
import re
from typing import Any

from sqlalchemy.orm import Session

from web.backend.models import User
from web.backend.normalization import normalize_book_request
from web.backend.pipeline_jobs import get_or_create_user_config, _api_keys_by_provider
from web.backend.schemas import BookRequest

from llm_provider import build_openai_client, DEFAULT_GOOGLE_BASE_URL, DEFAULT_GROQ_BASE_URL, DEFAULT_OLLAMA_BASE_URL, json_response_format_kwargs


SYSTEM_PROMPT = """\
You are an expert AI assistant that configures an automated book generation pipeline.
The user will provide a natural language request for a book they want to write.
Your job is to extract their intent and map it to a structured JSON object matching the BookRequest schema.

Here is the exact structure you MUST output:
{
  "topic": "string (the main subject of the book)",
  "audience": "string (who the book is for)",
  "tone": "string (e.g., formal, clear and supportive, academic, conversational)",
  "book_type": "auto | textbook | practice_workbook | course_companion | implementation_guide | reference_handbook | conceptual_guide | exam_prep",
  "theory_practice_balance": "auto | theory_heavy | balanced | practice_heavy | implementation_heavy",
  "pedagogy_style": "auto | german_theoretical | indian_theory_then_examples | socratic | exam_oriented | project_based",
  "source_usage": "auto | primary_curriculum | supplemental | example_inspiration",
  "exercise_strategy": "auto | none | extract_patterns | worked_examples | practice_sets",
  "goals": ["array of specific learning goals or user objectives"],
  "project_based": boolean,
  "running_project_description": "string (optional description of the project) or null",
  "code_density": "none | low | medium | high",
  "example_density": "high | medium | low",
  "diagram_density": "high | medium | low",
  "max_section_words": integer (150 to 2000, optional) or null,
  "force_web_research": boolean,
  "urls": ["array of strings (ONLY URLs EXPLICITLY PROVIDED in the user prompt. DO NOT invent URLs)"],
  "language_request": "string (optional language instruction) or null",
  "generation_contract": {
    "depth_level": "surface | intermediate | deep | exhaustive (or null)",
    "implementation_style": "conceptual_only | pseudocode | recipe_steps | file_by_file | project_progressive | argument_driven | case_study_playbook | workbook | visual_textbook | reference (or null)",
    "section_style": "academic | conversational | handbook | tutorial | reference | file_by_file_implementation | academic_argument | case_study_playbook | visual_textbook | workbook (or null)",
    "code_artifact_policy": "no_code | pseudocode_only | minimal_runnable | file_labeled_code_required (or null)",
    "diagram_style": "none | conceptual | architecture | data_flow | comparison_matrix | architecture_sequence_schema_deployment | concept_maps_decision_trees_checklists | argument_maps_comparison_matrices | timelines_cause_effect_maps | frameworks_matrices_funnels (or null)",
    "source_strictness": "low | medium | high | primary_sources_required (or null)",
    "evidence_standard": "anecdotal | curated | primary_source | peer_reviewed (or null)",
    "showcase_candidate": boolean,
    "required_stack": ["technologies the user explicitly mentions"],
    "forbidden_content": ["things the user says to avoid"],
    "project_artifacts": ["deliverables like folder tree, source files, tests"],
    "required_outputs": ["output types like definitions, exercises, timelines"],
    "success_criteria": ["what makes the book successful"],
    "target_reader_outcome": "string (what the reader should achieve) or null",
    "citation_policy": "string (citation approach) or null",
    "visual_policy": "string (diagram policy) or null",
    "notation_system": "string (e.g. LaTeX) or null"
  }
}

RULES:
1. The LLM parser should never set code_density above none for non-technical books (psychology, philosophy, history, business, self-help, education) unless the user explicitly asks for code.
2. Explicit "no code" (or without code, no programming, no YAML, no terminal commands) always means code_density="none" and generation_contract.code_artifact_policy="no_code". This applies even to technical topics!
3. Explicit "diagram-heavy" or "visual" always means diagram_density="high".
4. Explicit "homepage", "showcase", or "polished" always means generation_contract.showcase_candidate=true. Also output "target_quality_score": 80 (or higher if requested), "auto_repair": true, "sample_first": true, and "quality_mode": "full_auto_repair" at the top level.
5. Technical implementation guides with "code-heavy" must use generation_contract.code_artifact_policy="file_labeled_code_required" and implementation_style="file_by_file".
6. required_stack must include every technology explicitly named by the user in the prompt.
7. required_outputs must preserve requested artifacts such as worksheets, tests, diagrams, timelines, checklists, canvases, etc.
8. The "urls" array must ONLY contain URLs the user literally pasted. DO NOT invent URLs.

EXAMPLES:

User: "Create an evidence-based psychology handbook about building healthy study habits for university students. Keep it practical and supportive, but do not diagnose mental health conditions or make clinical treatment claims."
Output:
{
  "topic": "Healthy study habits",
  "audience": "University students",
  "tone": "Practical and supportive",
  "book_type": "reference_handbook",
  "theory_practice_balance": "practice_heavy",
  "pedagogy_style": "auto",
  "source_usage": "supplemental",
  "exercise_strategy": "worked_examples",
  "goals": ["Build healthy study habits", "Improve academic performance"],
  "project_based": false,
  "running_project_description": null,
  "code_density": "none",
  "example_density": "high",
  "diagram_density": "medium",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null,
  "generation_contract": {
    "depth_level": "intermediate",
    "implementation_style": "conceptual_only",
    "section_style": "handbook",
    "code_artifact_policy": "no_code",
    "diagram_style": "concept_maps_decision_trees_checklists",
    "source_strictness": "high",
    "evidence_standard": "peer_reviewed",
    "showcase_candidate": false,
    "required_stack": [],
    "forbidden_content": ["diagnosis", "clinical treatment advice", "fake studies", "fake statistics"],
    "project_artifacts": [],
    "required_outputs": ["evidence notes", "exercises", "reflection prompts", "habit trackers", "checklists"],
    "success_criteria": ["Evidence-based practical advice", "Supportive tone without medical claims"],
    "target_reader_outcome": "Develop sustainable study habits",
    "citation_policy": "Cite peer-reviewed studies",
    "visual_policy": null,
    "notation_system": null
  }
}

User: "Create a visual systems-thinking textbook. Use concept maps, feedback loops, and decision trees. No programming."
Output:
{
  "topic": "Systems thinking",
  "audience": "Students and professionals",
  "tone": "Academic yet visual",
  "book_type": "textbook",
  "theory_practice_balance": "balanced",
  "pedagogy_style": "auto",
  "source_usage": "primary_curriculum",
  "exercise_strategy": "practice_sets",
  "goals": ["Understand systems thinking concepts"],
  "project_based": false,
  "running_project_description": null,
  "code_density": "none",
  "example_density": "high",
  "diagram_density": "high",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null,
  "generation_contract": {
    "depth_level": "intermediate",
    "implementation_style": "visual_textbook",
    "section_style": "visual_textbook",
    "code_artifact_policy": "no_code",
    "diagram_style": "concept_maps_decision_trees_checklists",
    "source_strictness": "medium",
    "evidence_standard": "curated",
    "showcase_candidate": false,
    "required_stack": [],
    "forbidden_content": ["code examples", "programming filler", "terminal commands"],
    "project_artifacts": [],
    "required_outputs": ["concept maps", "feedback loop diagrams", "decision trees", "worksheets"],
    "success_criteria": ["Highly visual explanations"],
    "target_reader_outcome": "Apply systems thinking using visual tools",
    "citation_policy": null,
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}

User: "Build a production-ready URL shortener API showcase with FastAPI, PostgreSQL, SQLAlchemy, Alembic, Docker, Docker Compose, and pytest. Code-heavy, diagram-heavy, polished, for my portfolio."
Output:
{
  "topic": "Production-ready URL shortener API",
  "audience": "Developers reviewing a portfolio",
  "tone": "Technical and professional",
  "book_type": "implementation_guide",
  "theory_practice_balance": "implementation_heavy",
  "pedagogy_style": "project_based",
  "source_usage": "auto",
  "exercise_strategy": "practice_sets",
  "goals": ["Showcase a complete API build"],
  "project_based": true,
  "running_project_description": "A production URL shortener with FastAPI and Postgres",
  "code_density": "high",
  "example_density": "high",
  "diagram_density": "high",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null,
  "target_quality_score": 80,
  "auto_repair": true,
  "sample_first": true,
  "quality_mode": "full_auto_repair",
  "generation_contract": {
    "depth_level": "deep",
    "implementation_style": "file_by_file",
    "section_style": "file_by_file_implementation",
    "code_artifact_policy": "file_labeled_code_required",
    "diagram_style": "architecture_sequence_schema_deployment",
    "source_strictness": "medium",
    "evidence_standard": "curated",
    "showcase_candidate": true,
    "required_stack": ["FastAPI", "PostgreSQL", "SQLAlchemy", "Alembic", "Docker", "Docker Compose", "pytest"],
    "forbidden_content": ["broken code", "fake APIs", "disconnected snippets", "unlabeled code blocks", "placeholder code", "generic filler"],
    "project_artifacts": ["folder tree", "source files", "tests", "config files", "Dockerfile", "docker-compose.yml", "deployment checklist"],
    "required_outputs": ["folder tree", "source files", "config files", "tests", "verification commands", "troubleshooting checklist"],
    "success_criteria": ["homepage showcase-ready", "polished final manuscript", "coherent book arc", "no generic filler"],
    "target_reader_outcome": "Understand a production API architecture",
    "citation_policy": null,
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}

User: "Create a conceptual guide explaining Kubernetes architecture for product managers. Use diagrams and analogies, but no code, no YAML, and no terminal commands."
Output:
{
  "topic": "Kubernetes architecture for product managers",
  "audience": "Product managers",
  "tone": "Clear, conceptual, and analogy-driven",
  "book_type": "conceptual_guide",
  "theory_practice_balance": "theory_heavy",
  "pedagogy_style": "auto",
  "source_usage": "auto",
  "exercise_strategy": "none",
  "goals": ["Explain Kubernetes conceptually without technical implementation"],
  "project_based": false,
  "running_project_description": null,
  "code_density": "none",
  "example_density": "high",
  "diagram_density": "high",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null,
  "generation_contract": {
    "depth_level": "surface",
    "implementation_style": "conceptual_only",
    "section_style": "conversational",
    "code_artifact_policy": "no_code",
    "diagram_style": "architecture_sequence_schema_deployment",
    "source_strictness": "medium",
    "evidence_standard": "curated",
    "showcase_candidate": false,
    "required_stack": ["Kubernetes"],
    "forbidden_content": ["YAML", "terminal commands", "code examples", "programming filler", "shell commands"],
    "project_artifacts": [],
    "required_outputs": ["architecture diagrams", "concept maps"],
    "success_criteria": ["Clear analogies for non-engineers"],
    "target_reader_outcome": "Confidently discuss Kubernetes with engineering teams",
    "citation_policy": null,
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}

User: "Write a research-grounded guide on digital minimalism using https://example.com/minimal and https://example.org/focus. No fake quotes."
Output:
{
  "topic": "Digital minimalism",
  "audience": "General readers",
  "tone": "Research-grounded and practical",
  "book_type": "conceptual_guide",
  "theory_practice_balance": "balanced",
  "pedagogy_style": "auto",
  "source_usage": "supplemental",
  "exercise_strategy": "worked_examples",
  "goals": ["Reduce screen time", "Implement digital minimalism"],
  "project_based": false,
  "running_project_description": null,
  "code_density": "none",
  "example_density": "medium",
  "diagram_density": "medium",
  "max_section_words": null,
  "force_web_research": true,
  "urls": ["https://example.com/minimal", "https://example.org/focus"],
  "language_request": null,
  "generation_contract": {
    "depth_level": "intermediate",
    "implementation_style": "conceptual_only",
    "section_style": "conversational",
    "code_artifact_policy": "no_code",
    "diagram_style": "concept_maps_decision_trees_checklists",
    "source_strictness": "high",
    "evidence_standard": "curated",
    "showcase_candidate": false,
    "required_stack": [],
    "forbidden_content": ["fake studies", "fake statistics", "unsupported claims", "fake quotes"],
    "project_artifacts": [],
    "required_outputs": ["reflection prompts", "habit trackers"],
    "success_criteria": ["Accurate use of provided URLs"],
    "target_reader_outcome": "Establish intentional technology habits",
    "citation_policy": "Cite provided sources accurately",
    "visual_policy": null,
    "notation_system": null
  }
}

User: "Create a polished homepage showcase book about AI-assisted learning. Use full quality mode, sample first, auto repair, and target a quality score above 85. Make it diagram-heavy and no-code."
Output:
{
  "topic": "AI-assisted learning",
  "audience": "Educators and lifelong learners",
  "tone": "Visionary, polished, and practical",
  "book_type": "conceptual_guide",
  "theory_practice_balance": "balanced",
  "pedagogy_style": "auto",
  "source_usage": "auto",
  "exercise_strategy": "worked_examples",
  "goals": ["Demonstrate best practices in AI-assisted learning"],
  "project_based": false,
  "running_project_description": null,
  "code_density": "none",
  "example_density": "high",
  "diagram_density": "high",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null,
  "target_quality_score": 85,
  "auto_repair": true,
  "sample_first": true,
  "quality_mode": "full_auto_repair",
  "generation_contract": {
    "depth_level": "intermediate",
    "implementation_style": "conceptual_only",
    "section_style": "conversational",
    "code_artifact_policy": "no_code",
    "diagram_style": "concept_maps_decision_trees_checklists",
    "source_strictness": "high",
    "evidence_standard": "curated",
    "showcase_candidate": true,
    "required_stack": [],
    "forbidden_content": ["code examples", "programming filler", "terminal commands", "generic filler", "placeholder text", "internal QA text", "weak diagrams", "fake sources", "unsupported statistics"],
    "project_artifacts": [],
    "required_outputs": ["concept maps", "frameworks"],
    "success_criteria": ["homepage showcase-ready", "polished final manuscript", "coherent book arc", "no generic filler"],
    "target_reader_outcome": "Integrate AI effectively into learning workflows",
    "citation_policy": null,
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}
"""


def extract_json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    
    # Try to find JSON within markdown code blocks
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    # Fallback: try to find the outermost curly braces
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        try:
            return json.loads(text[start_idx:end_idx+1])
        except json.JSONDecodeError:
            pass
            
    # If all else fails, try direct parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError(f"Could not parse valid JSON from LLM response. Response snippet: {text[:200]}")


def parse_user_prompt(db: Session, user: User, prompt: str) -> dict[str, Any]:
    config = get_or_create_user_config(db, user)
    settings = config.settings or {}
    
    provider = settings.get("llm_provider", "google")
    api_keys = _api_keys_by_provider(db, user=user)
    
    api_key = api_keys.get(provider)
    if not api_key:
        raise ValueError(f"Missing API key for provider: {provider}")

    model = settings.get(f"planner_{provider}_model")
    if not model:
        # Fallback to defaults
        if provider == "google":
            model = "gemini-2.5-flash-lite"
        elif provider == "groq":
            model = "openai/gpt-oss-120b"
        elif provider == "ollama":
            model = "gpt-oss:120b"
        else:
            raise ValueError(f"Unknown provider: {provider}")

    base_urls = {
        "google": DEFAULT_GOOGLE_BASE_URL,
        "groq": DEFAULT_GROQ_BASE_URL,
        "ollama": DEFAULT_OLLAMA_BASE_URL,
    }
    base_url = base_urls[provider]
    
    client = build_openai_client(api_key=api_key, base_url=base_url)
    
    from llm_provider import build_chat_messages
    messages = build_chat_messages(model=model, system_prompt=SYSTEM_PROMPT, user_prompt=f"User Request: {prompt}")

    import logging
    logger = logging.getLogger(__name__)
    content = ""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            **json_response_format_kwargs(model)
        )
        content = response.choices[0].message.content or ""
        if not content:
            raise ValueError("LLM returned empty response")
            
        parsed = extract_json_from_text(content)
        normalized = normalize_book_request(parsed, original_prompt=prompt)
        validated = BookRequest.model_validate(normalized)
        return validated.model_dump()
    except Exception as e:
        logger.exception("LLM parse or validation failed, using deterministic fallback")
        
        # Build safe fallback dict
        safe_topic = prompt.split('.')[0][:100] if prompt else "Unknown Topic"
        is_tech = bool(re.search(r'\b(code|programming|software|api)\b', prompt, re.IGNORECASE))
        
        fallback_dict = {
            "topic": safe_topic,
            "audience": "General readers",
            "tone": "Clear and professional",
            "book_type": "conceptual_guide",
            "theory_practice_balance": "balanced",
            "pedagogy_style": "auto",
            "source_usage": "auto",
            "exercise_strategy": "worked_examples",
            "goals": ["Understand the topic", "Apply the ideas practically"],
            "code_density": "medium" if is_tech else "none",
            "example_density": "high",
            "diagram_density": "medium",
            "force_web_research": False,
            "urls": [],
            "generation_contract": {}
        }
        
        normalized_fallback = normalize_book_request(fallback_dict, original_prompt=prompt)
        validated_fallback = BookRequest.model_validate(normalized_fallback)
        return validated_fallback.model_dump()
