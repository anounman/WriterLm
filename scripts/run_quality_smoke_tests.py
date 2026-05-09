import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from planner_agent.schemas import BookPlan, ChapterPlan, SectionPlan, SectionContentRequirements
from quality.book_contract import classify_book_contract
from quality.repair_loop import run_quality_repair_loop
from quality.validator_registry import select_validators
from orchestration.parallel_section_pipeline import run_parallel_section_pipeline, ParallelSectionPipelineConfig
from orchestration.continuity_section_pipeline import run_continuity_section_pipeline
from notes_synthesizer.llm import GroqStructuredLLM as NotesLLM
from writer.llm import GroqStructuredLLM as WriterLLM
from reviewer.llm_client import build_reviewer_llm_client
from llm_provider import resolve_openai_compatible_config, get_default_models_for_layer, get_legacy_model_env_names_by_provider

DOMAINS = [
    {
        "id": "psychology",
        "topic": "building healthy study habits for university students",
        "audience": "beginners",
        "tone": "supportive and evidence-based",
        "goals": ["explain habits", "Avoid diagnosis or clinical claims"],
        "expect_validators": ["research_method_caution_validator", "safety_language_validator"],
        "not_expect_validators": ["code_validator"],
        "compare_profiles": True,
        "mock_claims": [
            "You must use this specific study schedule to cure ADHD.",  # Should trigger safety/diagnosis rules
            "Research proves this method guarantees straight As."       # Should trigger overclaim
        ]
    },
    {
        "id": "philosophy",
        "topic": "free will, determinism, compatibilism, and moral responsibility",
        "audience": "advanced students",
        "tone": "academic",
        "goals": ["explain determinism", "discuss free will"],
        "expect_validators": ["argument_validator"],
        "not_expect_validators": ["chronology_validator", "code_validator"],
        "compare_profiles": False,
        "mock_claims": [
            "Kant said: 'Free will is an illusion'.", # Fake quote
            "This section explores compatibilism." # Template filler
        ]
    },
    {
        "id": "history",
        "topic": "causes and consequences of the French Revolution",
        "audience": "beginners",
        "tone": "clear and educational",
        "goals": ["cover causes", "cover consequences"],
        "expect_validators": ["chronology_validator"],
        "not_expect_validators": ["code_validator"],
        "compare_profiles": False,
        "mock_claims": [
            "The revolution began on July 14, 1800.", # Wrong date
            "QA gate found validation problems in this section." # Forbidden string
        ]
    },
    {
        "id": "business",
        "topic": "product positioning and go-to-market strategy",
        "audience": "founders",
        "tone": "direct and practical",
        "goals": ["explain positioning", "give go-to-market plan"],
        "expect_validators": ["case_study_validator", "procedure_validator"],
        "not_expect_validators": [],
        "compare_profiles": False,
        "mock_claims": [
            "Company X increased revenue by 500%.", # Unmarked fictional case
            "Overall, we can see this works." # Template filler
        ]
    },
    {
        "id": "tech",
        "topic": "building a small REST API with authentication and tests",
        "audience": "intermediate software engineers",
        "tone": "practical",
        "goals": ["build REST API", "add authentication", "add tests"],
        "expect_validators": ["code_validator", "procedure_validator"],
        "not_expect_validators": [],
        "compare_profiles": True,
        "mock_claims": [
            "```\ndef broken_code()", # Broken code
            "The expected result is not just that the code runs." # Template filler
        ]
    }
]

def create_mock_bundle(domain_config: dict) -> tuple[dict[str, Any], BookPlan, dict]:
    request = {
        "topic": domain_config["topic"],
        "audience": domain_config["audience"],
        "goals": domain_config["goals"],
        "tone": domain_config["tone"],
        "depth": "intermediate"
    }
    
    # We create a 1-chapter, 2-section book to keep the test extremely fast.
    plan = BookPlan(
        title=domain_config["topic"],
        audience=domain_config["audience"],
        tone=domain_config["tone"],
        depth="intermediate",
        chapters=[
            ChapterPlan(
                chapter_number=1,
                title="Introduction and Setup",
                chapter_goal="Introduce the concepts",
                sections=[
                    SectionPlan(
                        title="Core Concepts",
                        goal="Explain the basics",
                        key_questions=["What is it?"],
                        estimated_words=150,
                        content_requirements=SectionContentRequirements(must_include_code=("tech" in domain_config["id"]), must_include_example=True)
                    ),
                    SectionPlan(
                        title="Practical Application",
                        goal="Apply the concepts",
                        key_questions=["How to apply?"],
                        estimated_words=150,
                        content_requirements=SectionContentRequirements(must_include_code=("tech" in domain_config["id"]), must_include_example=True)
                    )
                ]
            )
        ]
    )
    contract = classify_book_contract(request, plan)
    
    sections = []
    for i, s in enumerate(plan.chapters[0].sections):
        # We inject the mock claims into the knowledge map so the Notes/Writer LLM uses them!
        mock_claim = domain_config["mock_claims"][i] if i < len(domain_config["mock_claims"]) else ""
        
        packet = {
            "packet_id": f"sec_1_{i}",
            "task_id": f"sec_1_{i}",
            "section_id": s.title,
            "chapter_id": "1",
            "section_title": s.title,
            "objective": s.goal,
            "knowledge_map": {
                "key_claims": [{"label": "Fact", "content": f"Ensure you include this text verbatim: '{mock_claim}'", "supporting_source_ids": []}]
            },
            "writing_guidance": ["Please include the provided key claim literally in your output."]
        }
        sections.append(packet)
        
    chapter_research = {
        "chapter_id": "1",
        "chapter_title": "Introduction and Setup",
        "section_packets": sections
    }
    
    payload = {
        "book_plan": plan.model_dump(mode="json"),
        "chapters": [chapter_research],
        "book_contract": contract.model_dump(mode="json")
    }
    return payload, plan, request, contract

def get_llms():
    notes_config = resolve_openai_compatible_config(
        layer="notes",
        default_models=get_default_models_for_layer("notes"),
        legacy_env_names_by_provider=get_legacy_model_env_names_by_provider()
    )
    writer_config = resolve_openai_compatible_config(
        layer="writer",
        default_models=get_default_models_for_layer("writer"),
        legacy_env_names_by_provider=get_legacy_model_env_names_by_provider()
    )
    return (
        lambda: NotesLLM(api_key=notes_config.api_key, model=notes_config.model, base_url=notes_config.base_url),
        lambda: WriterLLM(api_key=writer_config.api_key, model=writer_config.model, base_url=writer_config.base_url),
        build_reviewer_llm_client
    )

def run_smoke_tests():
    OUTPUT_DIR = REPO_ROOT / "outputs" / "smoke_tests"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    notes_llm, writer_llm, reviewer_client = get_llms()
    results = []

    for domain in DOMAINS:
        print(f"\n==============================================")
        print(f"Testing domain: {domain['id']}")
        
        payload, plan, request, contract = create_mock_bundle(domain)
        
        # 1. Check Validator activations
        active_validators = [v.name for v in select_validators(contract)]
        v_ok = True
        for ev in domain["expect_validators"]:
            if ev not in active_validators:
                print(f"  [FAIL] Expected validator '{ev}' not active.")
                v_ok = False
        for nev in domain["not_expect_validators"]:
            if nev in active_validators:
                print(f"  [FAIL] Did not expect validator '{nev}' to be active.")
                v_ok = False
                
        if v_ok:
            print(f"  [PASS] Validator activations correct.")
        
        profiles_to_test = ["budget", "full"] if domain.get("compare_profiles") else ["budget"]
        domain_results = {}
        
        for profile in profiles_to_test:
            print(f"\n  Running '{profile}' profile...")
            run_dir = OUTPUT_DIR / f"{domain['id']}_{profile}"
            run_dir.mkdir(parents=True, exist_ok=True)
            
            # Save contract
            with open(run_dir / "book_contract.json", "w") as f:
                json.dump(contract.model_dump(mode="json"), f, indent=2)
            
            if profile == "budget":
                res = run_parallel_section_pipeline(
                    research_bundle_payload=payload,
                    book_title=plan.title,
                    run_id=domain["id"],
                    notes_llm_factory=notes_llm,
                    writer_llm_factory=writer_llm,
                    reviewer_llm_client_factory=reviewer_client,
                    config=ParallelSectionPipelineConfig(max_workers=1)
                )
            else:
                res = run_continuity_section_pipeline(
                    research_bundle_payload=payload,
                    planner_input=request,
                    book_plan=plan,
                    book_title=plan.title,
                    run_id=domain["id"],
                    run_dir=run_dir,
                    notes_llm_factory=notes_llm,
                    writer_llm_factory=writer_llm,
                    reviewer_llm_client_factory=reviewer_client,
                    config=ParallelSectionPipelineConfig(max_workers=1)
                )
            
            # Run repair loop
            repair = run_quality_repair_loop(review_bundle=res.review_bundle, contract=contract)
            qa_report = repair.qa_report
            repaired_bundle = repair.review_bundle
            
            with open(run_dir / "qa_report.json", "w") as f:
                json.dump(qa_report, f, indent=2)
                
            with open(run_dir / "final_manuscript.txt", "w") as f:
                for s in repaired_bundle.sections:
                    f.write(f"\n--- {s.section_input.section_title} ---\n")
                    f.write(s.section_output.reviewed_content)
                    
            qa_passed = qa_report.get("qa_passed", False)
            quality_score = qa_report.get("scores", {}).get("quality_score", 0)
            
            print(f"  [{'PASS' if qa_passed else 'FAIL'}] QA Passed: {qa_passed}")
            print(f"  Score: {quality_score}/100")
            
            # Check for forbidden strings
            forbidden_strings = ["QA gate found validation problems", "Unresolved Gaps", "TODO", "FIXME", "placeholder", "citation needed"]
            template_fillers = ["the expected result is not just that the code runs", "change one input, parameter, or file", "this matters because each step should fail loudly and locally", "the printed output is your first test", "this section explores", "as an ai"]
            
            has_forbidden = False
            for s in repaired_bundle.sections:
                txt = s.section_output.reviewed_content.lower()
                for fb in forbidden_strings + template_fillers:
                    if fb.lower() in txt:
                        print(f"  [FAIL] Forbidden string found in final text: '{fb}'")
                        has_forbidden = True
                        
            if not has_forbidden:
                print("  [PASS] No forbidden strings or template fillers in final text.")
            
            domain_results[profile] = {
                "qa_passed": qa_passed,
                "score": quality_score,
                "clean": not has_forbidden,
                "validators_ok": v_ok
            }
            
        if len(profiles_to_test) > 1:
            score_b = domain_results["budget"]["score"]
            score_f = domain_results["full"]["score"]
            if score_f >= score_b:
                print(f"  [PASS] Full profile score ({score_f}) >= Budget score ({score_b})")
            else:
                print(f"  [FAIL] Full profile score ({score_f}) < Budget score ({score_b})")
                
        results.append({"domain": domain["id"], "results": domain_results})

    print("\n\n==== SUMMARY ====")
    for r in results:
        dom = r["domain"]
        for prof, metrics in r["results"].items():
            print(f"{dom} ({prof}): Score={metrics['score']}, Clean={metrics['clean']}, ValidatorsOK={metrics['validators_ok']}, QAPassed={metrics['qa_passed']}")

if __name__ == "__main__":
    run_smoke_tests()
