import json
import re
from typing import Any

from sqlalchemy.orm import Session

from web.backend.models import User
from web.backend.normalization import normalize_book_request
from web.backend.pipeline_jobs import get_or_create_user_config, _api_keys_by_provider
from web.backend.schemas import BookRequest

from llm_provider import build_openai_client, DEFAULT_GOOGLE_BASE_URL, DEFAULT_GROQ_BASE_URL, json_response_format_kwargs


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
1. Use code_density="none" for non-technical books (psychology, philosophy, history, business, self-help, education) unless the user explicitly asks for code.
2. Use code_density="medium" or "high" for technical implementation/programming books.
3. The "urls" array must ONLY contain URLs the user literally pasted. DO NOT invent URLs.
4. Infer generation_contract fields from the user's intent, domain, and constraints.
5. Set showcase_candidate=true when the user mentions "showcase", "homepage", "polished", or "publication-ready".
6. For philosophy/ethics books: implementation_style="argument_driven", section_style="academic_argument", code_artifact_policy="no_code".
7. For history books: code_artifact_policy="no_code", diagram_style="timelines_cause_effect_maps".
8. For psychology/self-help: code_artifact_policy="no_code", forbidden_content should include "diagnosis" and "clinical treatment advice".
9. For business/strategy: implementation_style="case_study_playbook", code_artifact_policy="no_code".
10. For technical implementation guides: implementation_style="file_by_file", code_artifact_policy="file_labeled_code_required".
11. required_stack should only include technologies the user explicitly names.

EXAMPLES:

User: "I want to write a polished showcase book on focus and deep work for my homepage. No code, research-backed, high quality."
Output:
{
  "topic": "Focus and deep work in the modern world",
  "audience": "Professionals and knowledge workers",
  "tone": "Calm, professional, and polished",
  "book_type": "conceptual_guide",
  "theory_practice_balance": "balanced",
  "pedagogy_style": "auto",
  "source_usage": "supplemental",
  "exercise_strategy": "worked_examples",
  "goals": ["Build sustainable focus habits", "Navigate distraction in digital environments"],
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
    "depth_level": "deep",
    "implementation_style": "conceptual_only",
    "section_style": "conversational",
    "code_artifact_policy": "no_code",
    "diagram_style": "concept_maps_decision_trees_checklists",
    "source_strictness": "high",
    "evidence_standard": "curated",
    "showcase_candidate": true,
    "required_stack": [],
    "forbidden_content": ["code examples", "programming filler", "terminal commands", "diagnosis", "clinical treatment advice"],
    "project_artifacts": [],
    "required_outputs": ["evidence notes", "exercises", "reflection prompts", "checklists"],
    "success_criteria": ["homepage showcase-ready", "polished final manuscript", "coherent book arc", "no generic filler"],
    "target_reader_outcome": "Sustainably improve focus and productivity without burnout",
    "citation_policy": "Cite key studies inline; attribute frameworks to original authors",
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}

User: "Build a production-ready URL shortener API with FastAPI, PostgreSQL, Docker, and tests. Code-heavy and diagram-heavy. Use https://fastapi.tiangolo.com as reference."
Output:
{
  "topic": "Building a production-ready URL shortener API",
  "audience": "Intermediate to advanced Python backend developers",
  "tone": "Technical, precise, and implementation-focused",
  "book_type": "implementation_guide",
  "theory_practice_balance": "implementation_heavy",
  "pedagogy_style": "project_based",
  "source_usage": "supplemental",
  "exercise_strategy": "practice_sets",
  "goals": ["Build a complete URL shortener API from scratch", "Implement authentication, rate limiting, and analytics", "Containerize and deploy"],
  "project_based": true,
  "running_project_description": "A production-ready URL shortener service with FastAPI, PostgreSQL, and Docker",
  "code_density": "high",
  "example_density": "high",
  "diagram_density": "high",
  "max_section_words": null,
  "force_web_research": false,
  "urls": ["https://fastapi.tiangolo.com"],
  "language_request": null,
  "generation_contract": {
    "depth_level": "deep",
    "implementation_style": "file_by_file",
    "section_style": "file_by_file_implementation",
    "code_artifact_policy": "file_labeled_code_required",
    "diagram_style": "architecture_sequence_schema_deployment",
    "source_strictness": null,
    "evidence_standard": null,
    "showcase_candidate": false,
    "required_stack": ["FastAPI", "PostgreSQL", "Docker", "pytest"],
    "forbidden_content": ["broken code", "fake APIs", "disconnected snippets", "unlabeled code blocks", "placeholder code"],
    "project_artifacts": ["folder tree", "source files", "tests", "config files", "Dockerfile", "docker-compose.yml", "deployment checklist"],
    "required_outputs": ["folder tree", "source files", "config files", "tests", "verification commands", "troubleshooting checklist"],
    "success_criteria": ["Every code block is labeled with file path", "Project builds and runs end-to-end"],
    "target_reader_outcome": "Deploy a working URL shortener API in production",
    "citation_policy": null,
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}

User: "Write a philosophy book about free will and moral responsibility, suitable for advanced readers."
Output:
{
  "topic": "Free will and moral responsibility",
  "audience": "Advanced readers and philosophy students",
  "tone": "Rigorous, measured, and intellectually honest",
  "book_type": "conceptual_guide",
  "theory_practice_balance": "theory_heavy",
  "pedagogy_style": "socratic",
  "source_usage": "primary_curriculum",
  "exercise_strategy": "none",
  "goals": ["Compare major positions on free will", "Analyze objections and counterarguments", "Evaluate moral responsibility under each framework"],
  "project_based": false,
  "running_project_description": null,
  "code_density": "none",
  "example_density": "medium",
  "diagram_density": "medium",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null,
  "generation_contract": {
    "depth_level": "deep",
    "implementation_style": "argument_driven",
    "section_style": "academic_argument",
    "code_artifact_policy": "no_code",
    "diagram_style": "argument_maps_comparison_matrices",
    "source_strictness": "primary_sources_required",
    "evidence_standard": "primary_source",
    "showcase_candidate": false,
    "required_stack": [],
    "forbidden_content": ["fake quotes", "unsupported attribution", "unclear terminology", "code examples"],
    "project_artifacts": [],
    "required_outputs": ["definitions", "argument maps", "objections", "counterarguments", "conclusion summaries"],
    "success_criteria": ["Every major position fairly represented", "Clear distinction between author analysis and source claims"],
    "target_reader_outcome": "Critically evaluate free will positions and construct informed arguments",
    "citation_policy": "Attribute all positions to original philosophers; cite primary texts",
    "visual_policy": null,
    "notation_system": null
  }
}

User: "A history book on the French Revolution for general readers, with timelines and maps."
Output:
{
  "topic": "The French Revolution",
  "audience": "General readers interested in European history",
  "tone": "Narrative, clear, and engaging",
  "book_type": "conceptual_guide",
  "theory_practice_balance": "balanced",
  "pedagogy_style": "auto",
  "source_usage": "supplemental",
  "exercise_strategy": "none",
  "goals": ["Understand the causes, course, and consequences of the French Revolution", "Distinguish disputed interpretations"],
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
    "implementation_style": null,
    "section_style": "conversational",
    "code_artifact_policy": "no_code",
    "diagram_style": "timelines_cause_effect_maps",
    "source_strictness": "medium",
    "evidence_standard": "primary_source",
    "showcase_candidate": false,
    "required_stack": [],
    "forbidden_content": ["fake dates", "fake events", "invented quotes", "unsupported claims", "code examples"],
    "project_artifacts": [],
    "required_outputs": ["timelines", "chronology tables", "cause-effect maps", "disputed interpretation notes"],
    "success_criteria": ["Chronologically accurate", "Multiple interpretations presented fairly"],
    "target_reader_outcome": "Understand the French Revolution's causes, key events, and lasting impact",
    "citation_policy": "Cite primary and secondary historical sources",
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}

User: "A go-to-market playbook for first-time founders launching a B2B SaaS product."
Output:
{
  "topic": "Go-to-market strategy for B2B SaaS",
  "audience": "First-time founders and early-stage startup teams",
  "tone": "Practical, direct, and actionable",
  "book_type": "conceptual_guide",
  "theory_practice_balance": "practice_heavy",
  "pedagogy_style": "auto",
  "source_usage": "example_inspiration",
  "exercise_strategy": "worked_examples",
  "goals": ["Build a repeatable GTM playbook", "Validate product-market fit", "Design pricing and positioning"],
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
    "implementation_style": "case_study_playbook",
    "section_style": "case_study_playbook",
    "code_artifact_policy": "no_code",
    "diagram_style": "frameworks_matrices_funnels",
    "source_strictness": "medium",
    "evidence_standard": "curated",
    "showcase_candidate": false,
    "required_stack": [],
    "forbidden_content": ["fake real company case studies", "vague startup buzzwords", "unsupported market claims", "code examples"],
    "project_artifacts": [],
    "required_outputs": ["canvases", "decision tables", "checklists", "fictional case studies", "action plans"],
    "success_criteria": ["Actionable templates in every chapter", "Fictional examples clearly labeled"],
    "target_reader_outcome": "Launch a B2B SaaS product with a validated GTM strategy",
    "citation_policy": null,
    "visual_policy": "structured useful diagrams only",
    "notation_system": null
  }
}

User: "A visual systems-thinking textbook for university students with concept maps and exercises."
Output:
{
  "topic": "Systems thinking",
  "audience": "University students in engineering, business, and social sciences",
  "tone": "Academic yet accessible",
  "book_type": "textbook",
  "theory_practice_balance": "balanced",
  "pedagogy_style": "auto",
  "source_usage": "primary_curriculum",
  "exercise_strategy": "practice_sets",
  "goals": ["Understand feedback loops, emergence, and system archetypes", "Apply systems thinking to real-world problems"],
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
    "forbidden_content": ["code examples"],
    "project_artifacts": [],
    "required_outputs": ["concept maps", "exercises", "case studies", "feedback loop diagrams"],
    "success_criteria": ["Every chapter has visual aids", "Exercises test understanding"],
    "target_reader_outcome": "Apply systems thinking frameworks to analyze complex problems",
    "citation_policy": "Cite seminal systems thinking literature",
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
        else:
            raise ValueError(f"Unknown provider: {provider}")

    base_url = DEFAULT_GOOGLE_BASE_URL if provider == "google" else DEFAULT_GROQ_BASE_URL
    
    client = build_openai_client(api_key=api_key, base_url=base_url)
    
    from llm_provider import build_chat_messages
    messages = build_chat_messages(model=model, system_prompt=SYSTEM_PROMPT, user_prompt=f"User Request: {prompt}")

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        **json_response_format_kwargs(model)
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response")
        
    try:
        parsed = extract_json_from_text(content)
        # Apply deterministic normalization — this is the source of truth
        normalized = normalize_book_request(parsed, original_prompt=prompt)
        # Validate against schema and return the clean dict
        validated = BookRequest.model_validate(normalized)
        return validated.model_dump()
    except Exception as e:
        raise ValueError(f"Failed to parse LLM response into BookRequest: {e}\nResponse: {content[:200]}...") from e
