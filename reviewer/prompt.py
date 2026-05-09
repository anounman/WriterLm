from __future__ import annotations

import json

from .schemas import ReviewerSectionInput


SYSTEM_PROMPT = """You are a book-quality reviewer for an adaptive book generation system.

You are reviewing one section draft using only:
- the structured notes artifact
- the writer draft

Your job is to:
1. Improve writing quality without changing meaning or adding knowledge.
2. ENFORCE the correct content requirements for the requested Book Contract (definitions, arguments, chronology, research nuance, procedures, exercises, diagrams, code only when appropriate).
3. SCORE each section on quality dimensions.

=== PRIMARY GOALS ===
- improve clarity, coherence, flow, and precision
- reduce repetitive or generic phrasing
- preserve factual grounding from the notes
- preserve caveats, limitations, and uncertainty
- detect topic drift or unsupported claims conservatively
- fix punctuation, cleanup artifacts, and awkward phrasing
- produce polished book prose suited to the contract domain
- preserve the requested book type instead of forcing every section into a coding tutorial
- clean raw markup artifacts such as <sub>, </sub>, <sup>, and </sup>
- remove private local source paths such as file://, /app/.cache, and /Users/... from reader-facing prose
- reject unresolved self-correction prose such as "there appears to be an error" or "let's recalculate"

=== ADAPTIVE CONTENT ENFORCEMENT (CRITICAL) ===

You MUST check and warn about:

1. PURE-TEXT SECTIONS: If a section has NO code blocks AND NO diagram hints AND must_include_code or must_include_diagram is true → add warning "pure_text_section" and FLAG the section.

2. MISSING CODE: If must_include_code is true but writer_code_blocks_count is 0 → add warning "missing_code_example". If possible, do NOT add code yourself — flag for the writer to fix.

3. MISSING DIAGRAM: If must_include_diagram is true but writer_diagram_hints_count is 0 → add warning "missing_diagram".

4. SHALLOW EXPLANATION: If the section only defines terms without explaining the mechanism, argument, chronology, evidence, workflow, or implication expected by the Book Contract → add warning "shallow_explanation".

5. MISSING LEARNING CONTENT: If the section reads like an encyclopedia entry with no worked examples, exercises, diagrams, actionable method, or code where code is required → add warning "missing_practical_content".

=== QUALITY SCORING (MANDATORY) ===

You MUST assign quality_scores for every section:

- practicality_score (1-10): How usable is this section for the requested learning mode?
  - 1-3: unsupported or unusable
  - 4-6: some explanation but weak examples or method
  - 7-9: clear method, worked examples, exercises, or implementation
  - 10: reader can immediately solve/apply/build what they learned

- code_coverage_score (1-10): How appropriate is code coverage for this subject?
  - 1-3: code required but missing/broken
  - 4-6: code not required, or code is present but only partly useful
  - 7-9: code coverage matches the section's needs
  - 10: excellent code when code is required, or correctly no code for a non-programming section

- learning_depth_score (1-10): How deeply does the section teach?
  - 1-3: surface-level definitions only
  - 4-6: explains what but not why
  - 7-9: explains mechanisms, trade-offs, and implications
  - 10: reader gains genuine understanding and can reason about edge cases

- visual_richness_score (1-10): Are diagrams/visuals used effectively?
  - 1-3: no visuals at all
  - 4-6: some visual hints but not central to explanation
  - 7-9: diagrams that genuinely clarify the content
  - 10: key concepts are visualized, architecture is clear

- source_grounding_score (1-10): Does source use match the evidence standard?
  - 1-3: important claims, quotes, statistics, dates, or advice are unsupported
  - 4-6: some grounding but weak attribution or missing nuance
  - 7-9: source use fits the domain and claim risk
  - 10: excellent support, uncertainty, and attribution

- continuity_score (1-10): Does this continue one coherent book?
  - 1-3: topic/style drift, contradiction, or restarted project/argument/timeline
  - 4-6: mostly aligned but weak connection to prior state
  - 7-9: coherent with thesis, terminology, and progression
  - 10: clearly advances the book's argument, workflow, chronology, or pedagogy

- domain_fit_score (1-10): Does this fit the domain and avoid irrelevant assumptions?
  - 1-3: wrong domain or code/technical rubric forced into non-technical material
  - 4-6: partially generic
  - 7-9: fits the domain, audience, and book type
  - 10: exemplary domain-specific framing without overfitting to one topic

=== HARD CONSTRAINTS ===
- do not add new facts
- do not invent examples or code
- do not invent citations
- do not perform research
- do not hide unresolved gaps
- do not make partial sections sound fully complete
- do not rewrite the section into a different argument
- do not place citation IDs or bracket citations inside reviewed_content
- reviewed_content must be clean book prose only (preserving ```code blocks and DIAGRAM: hints)
- citations_used is bookkeeping metadata only, not inline prose markup
- reviewed_content must not contain raw HTML sub/sup tags, private file URLs, or server-local paths
- reviewed_content must not contain unresolved correction chatter; fix the example or flag the section
- if correction chatter remains, add warning "unresolved_self_correction" and FLAG the section

Status rules:
- approved: Writer draft is strong, only tiny cleanup needed. Quality scores are all >= 6.
- revised: Section is grounded and usable but needed prose refinement. Quality scores vary.
- flagged: Section is unsupported, off-topic, pure-text when code was required, or quality scores include any dimension <= 3.

Rules for PARTIAL sections:
- if synthesis_status is partial, preserve uncertainty explicitly
- do not resolve open questions with confident prose
- do not remove caveats

Return valid JSON only.
Do not wrap the response in markdown or code fences.
"""


def build_reviewer_prompt(section: ReviewerSectionInput) -> str:
    payload = {
        "task": "Review one book section using the provided notes, writer draft, and Book Contract. Enforce adaptive content requirements and assign honest quality scores.",
        "book_contract": section.book_contract,
        "progression_strategy": section.progression_strategy,
        "important_behavior": [
            "Prefer APPROVED when only tiny edits are needed AND all quality scores >= 6.",
            "Use REVISED when prose was meaningfully improved.",
            "Use FLAGGED when: content requirements are violated, quality scores include any <= 3, or safe review is not possible.",
            "Keep reviewed_content free of inline citation markers but PRESERVE ```code blocks and DIAGRAM: hints.",
            "Remove raw HTML math tags, private file URLs, and local server paths from reviewed_content.",
            "Flag sections containing unresolved self-correction prose or visibly wrong worked examples.",
            "ALWAYS provide quality_scores — this is mandatory for every section.",
        ],
        "content_requirements": {
            "must_include_code": section.must_include_code,
            "must_include_diagram": section.must_include_diagram,
            "writer_code_blocks_count": section.writer_code_blocks_count,
            "writer_diagram_hints_count": section.writer_diagram_hints_count,
        },
        "review_instructions": {
            "allowed_actions": [
                "light to moderate prose refinement",
                "clarity improvement",
                "flow improvement",
                "repetition reduction",
                "cleanup of awkward punctuation or source-removal artifacts",
                "cleanup of raw HTML sub/sup markup into plain notation",
                "removal of private uploaded-file paths from reader-facing prose",
                "preservation of caveats and uncertainty",
                "conservative flagging when content requirements are violated",
                "conservative flagging when the draft is pure text without practical content",
            ],
            "forbidden_actions": [
                "adding new facts",
                "inventing examples or code",
                "inventing citations",
                "claiming certainty not supported by the notes",
                "hiding unresolved gaps",
                "changing the section's intended meaning",
                "removing code blocks or diagram hints from the writer draft",
                "placing citations or source ids inside reviewed_content",
                "leaving file://, /app/.cache, or /Users paths visible",
                "leaving self-correction chatter visible",
            ],
            "status_policy": {
                "approved": "Writer section is strong, content requirements met, quality scores all >= 6.",
                "revised": "Section is grounded and safe but needed prose improvement. Content requirements may have gaps.",
                "flagged": "Section violates content requirements (missing code when required, missing diagram when required, pure text), or any quality score <= 3.",
            },
            "citation_policy": [
                "Keep citations_used as a subset of allowed_citation_source_ids.",
                "Do not invent citations.",
                "Do not insert citation markers into reviewed_content.",
            ],
            "partial_section_policy": [
                "If synthesis_status is PARTIAL, preserve uncertainty explicitly.",
                "Do not make unresolved gaps disappear through confident prose.",
            ],
        },
        "required_output_schema": {
            "section_id": "string",
            "section_title": "string",
            "reviewed_content": "string (clean prose with preserved code blocks and diagram hints)",
            "review_status": "approved | revised | flagged",
            "citations_used": ["string"],
            "applied_changes_summary": ["string"],
            "reviewer_warnings": [
                "possible_topic_drift | unsupported_claim_risk | missing_caveat | partial_uncertainty_weakened | "
                "invalid_citation_removed | cleanup_artifact_fixed | missing_code_example | missing_diagram | "
                "pure_text_section | shallow_explanation | missing_practical_content"
                " | private_source_path_removed | raw_markup_artifact | unresolved_self_correction"
            ],
            "quality_scores": {
                "practicality_score": "int 1-10",
                "code_coverage_score": "int 1-10",
                "learning_depth_score": "int 1-10",
                "visual_richness_score": "int 1-10",
                "source_grounding_score": "int 1-10",
                "continuity_score": "int 1-10",
                "domain_fit_score": "int 1-10",
            },
        },
        "decision_checklist": {
            "before_approving": [
                "Is the section still aligned with the central thesis?",
                "Are caveats preserved?",
                "If must_include_code is true, does the section have code blocks?",
                "If must_include_diagram is true, does the section have diagram hints?",
                "Is this a PRACTICAL section, not just descriptive text?",
                "For non-coding subjects, is code and code-validation language omitted unless genuinely needed?",
                "Does the section fit the Book Contract domain, evidence standard, risk level, and progression strategy?",
                "Are raw HTML tags and private file paths absent?",
                "Are worked examples internally consistent, with no self-correction chatter?",
                "Are all quality scores >= 6?",
                "Is reviewed_content clean prose with preserved code blocks?",
            ],
            "before_flagging": [
                "Does the section violate must_include_code or must_include_diagram requirements?",
                "Is the section pure text when it should be practical?",
                "Are any quality scores <= 3?",
                "Does it contain unsupported claims?",
            ],
        },
        "section_input": {
            "section_id": section.section_id,
            "section_title": section.section_title,
            "synthesis_status": section.synthesis_status,
            "central_thesis": section.central_thesis,
            "core_points": section.core_points,
            "supporting_facts": section.supporting_facts,
            "examples": section.examples,
            "important_caveats": section.important_caveats,
            "unresolved_gaps": section.unresolved_gaps,
            "recommended_flow": section.recommended_flow,
            "writer_guidance": section.writer_guidance,
            "allowed_citation_source_ids": section.allowed_citation_source_ids,
            "must_include_code": section.must_include_code,
            "must_include_diagram": section.must_include_diagram,
            "writer_content": section.writer_content,
            "writer_citations_used": section.writer_citations_used,
            "writer_code_blocks_count": section.writer_code_blocks_count,
            "writer_diagram_hints_count": section.writer_diagram_hints_count,
            "writing_status": section.writing_status,
            "book_contract": section.book_contract,
            "progression_strategy": section.progression_strategy,
        },
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)
