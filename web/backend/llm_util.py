import json
import re
from typing import Any

from sqlalchemy.orm import Session

from web.backend.models import User
from web.backend.pipeline_jobs import get_or_create_user_config, _api_keys_by_provider
from web.backend.schemas import BookRequest

from llm_provider import build_openai_client, DEFAULT_GOOGLE_BASE_URL, DEFAULT_GROQ_BASE_URL, json_response_format_kwargs


SYSTEM_PROMPT = """You are an expert AI assistant that configures an automated textbook generation pipeline.
The user will provide a natural language request for a book they want to write.
Your job is to extract their intent and map it to a structured JSON object matching the `BookRequest` schema.

Here is the exact structure you MUST output:
{
  "topic": "string (the main subject of the book)",
  "audience": "string (who the book is for)",
  "tone": "string (e.g., formal, clear and supportive, academic)",
  "book_type": "auto | textbook | practice_workbook | course_companion | implementation_guide | reference_handbook | conceptual_guide | exam_prep",
  "theory_practice_balance": "auto | theory_heavy | balanced | practice_heavy | implementation_heavy",
  "pedagogy_style": "auto | german_theoretical | indian_theory_then_examples | socratic | exam_oriented | project_based",
  "source_usage": "auto | primary_curriculum | supplemental | example_inspiration",
  "exercise_strategy": "auto | none | extract_patterns | worked_examples | practice_sets",
  "goals": ["array of specific learning goals or user objectives"],
  "project_based": boolean,
  "running_project_description": "string (optional description of the project) or null",
  "code_density": "high | medium | low",
  "example_density": "high | medium | low",
  "diagram_density": "high | medium | low",
  "max_section_words": integer (150 to 2000, optional) or null,
  "force_web_research": boolean,
  "urls": ["array of strings (ONLY URLs EXPLICITLY PROVIDED in the user prompt. DO NOT invent or hallucinate URLs)"],
  "language_request": "string (optional language instruction) or null"
}

If a specific detail is missing from their prompt, infer a reasonable professional default based on the topic.
CRITICAL INSTRUCTION: Under NO circumstances should you inject, invent, or hallucinate URLs. The "urls" array must ONLY contain URLs that the user literally pasted into their prompt. If no URLs are present in the text, return an empty array [].

EXAMPLES:

User: "Write an advanced implementation guide for deploying scalable infrastructure on AWS with high code density and a project-based approach."
Output:
{
  "topic": "Deploying scalable infrastructure on AWS",
  "audience": "Advanced software engineers and DevOps practitioners",
  "tone": "Technical, practical, and authoritative",
  "book_type": "implementation_guide",
  "theory_practice_balance": "implementation_heavy",
  "pedagogy_style": "project_based",
  "source_usage": "auto",
  "exercise_strategy": "practice_sets",
  "goals": [
    "Learn to deploy scalable infrastructure on AWS",
    "Understand best practices for DevOps and Cloud architecture"
  ],
  "project_based": true,
  "running_project_description": "Building and deploying a complete scalable web application infrastructure on AWS",
  "code_density": "high",
  "example_density": "high",
  "diagram_density": "high",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null
}

User: "Create a beginner-friendly Python textbook with lots of diagrams."
Output:
{
  "topic": "Introduction to Python Programming",
  "audience": "Absolute beginners with no prior programming experience",
  "tone": "Clear, supportive, and encouraging",
  "book_type": "textbook",
  "theory_practice_balance": "balanced",
  "pedagogy_style": "auto",
  "source_usage": "auto",
  "exercise_strategy": "worked_examples",
  "goals": [
    "Understand basic Python syntax and data structures",
    "Learn to write simple scripts and programs"
  ],
  "project_based": false,
  "running_project_description": null,
  "code_density": "medium",
  "example_density": "high",
  "diagram_density": "high",
  "max_section_words": null,
  "force_web_research": false,
  "urls": [],
  "language_request": null
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
        # Validate against schema and return the clean dict
        validated = BookRequest.model_validate(parsed)
        return validated.model_dump()
    except Exception as e:
        raise ValueError(f"Failed to parse LLM response into BookRequest: {e}\nResponse: {content[:200]}...")
