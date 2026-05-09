from __future__ import annotations

from researcher.schemas import EvidenceType, KnowledgeMapItem, SectionKnowledgeMap, SectionResearchPacket
from researcher.state import ResearcherState
from researcher.utils.ids import make_packet_id


class AssembleResearchPacketNode:
    """
    Assemble the final SectionResearchPacket for the current section.

    Responsibilities:
    - read final research artifacts from state
    - derive key concepts from evidence tags
    - collect open questions from coverage gaps
    - produce writing guidance for the next layer
    - write the final research packet back into state
    """

    def run(self, state: ResearcherState) -> ResearcherState:
        """
        Build the final research packet from the current researcher state.
        """
        if state.research_packet is not None:
            return state

        if state.research_task is None:
            state.add_error(
                "Cannot assemble research packet because research_task is missing."
            )
            return state

        if not state.evidence_items:
            state.add_error(
                "Cannot assemble research packet because evidence_items is empty."
            )
            return state

        section = state.research_task.section

        key_concepts = self._derive_key_concepts(state)
        open_questions = self._derive_open_questions(state)
        writing_guidance = self._build_writing_guidance(state)
        knowledge_map = self._build_knowledge_map(state)

        state.research_packet = SectionResearchPacket(
            packet_id=make_packet_id(section.section_id),
            task_id=state.research_task.task_id,
            section_id=section.section_id,
            chapter_id=section.chapter_id,
            section_title=section.section_title,
            objective=state.research_task.objective,
            key_concepts=key_concepts,
            evidence_items=state.evidence_items,
            sources=[
                source
                for source in state.source_registry
                if source.evidence_ids and not any("fetch_failed" in note for note in source.reliability_notes)
            ],
            knowledge_map=knowledge_map,
            coverage_report=state.coverage_report,
            open_questions=open_questions,
            writing_guidance=writing_guidance,
        )
        return state

    def _build_knowledge_map(self, state: ResearcherState) -> SectionKnowledgeMap:
        source_lookup = {
            source.source_id: source
            for source in state.source_registry
        }

        key_claims: list[KnowledgeMapItem] = []
        definitions: list[KnowledgeMapItem] = []
        examples: list[KnowledgeMapItem] = []
        conflicting_viewpoints: list[KnowledgeMapItem] = []
        uncertainty_flags: list[str] = []

        for index, evidence in enumerate(state.evidence_items[:20], start=1):
            source = source_lookup.get(evidence.source_id)
            item = KnowledgeMapItem(
                label=(evidence.tags[0] if evidence.tags else evidence.evidence_type.value),
                content=self._clean_text(evidence.summary or evidence.content),
                supporting_source_ids=[evidence.source_id] if evidence.source_id else [],
                source_reliability=self._source_reliability_note(source),
                source_freshness=self._source_freshness_note(source),
                uncertainty_flag="low confidence extraction" if evidence.confidence < 0.55 else None,
            )
            if item.uncertainty_flag:
                uncertainty_flags.append(f"{item.label}: {item.uncertainty_flag}")

            if evidence.evidence_type == EvidenceType.DEFINITION:
                definitions.append(item)
            elif evidence.evidence_type in {EvidenceType.EXAMPLE, EvidenceType.CASE_STUDY}:
                examples.append(item)
            elif evidence.evidence_type in {EvidenceType.WARNING, EvidenceType.INSIGHT}:
                conflicting_viewpoints.append(item)
            else:
                key_claims.append(item)

        if state.coverage_report is not None:
            uncertainty_flags.extend(
                f"Coverage gap: {self._clean_text(topic)}"
                for topic in state.coverage_report.missing_topics
                if self._clean_text(topic)
            )

        return SectionKnowledgeMap(
            key_claims=key_claims[:10],
            definitions=definitions[:8],
            examples=examples[:8],
            conflicting_viewpoints=conflicting_viewpoints[:6],
            open_questions=self._derive_open_questions(state),
            uncertainty_flags=self._clean_list(uncertainty_flags)[:8],
            recommended_framing=self._build_writing_guidance(state)[:8],
        )

    def _source_reliability_note(self, source) -> str | None:
        if source is None:
            return None
        if source.quality_score is not None:
            return f"quality_score={source.quality_score:.2f}"
        if source.reliability_notes:
            return "; ".join(source.reliability_notes[:2])
        return source.source_type.value

    def _source_freshness_note(self, source) -> str | None:
        if source is None:
            return None
        if source.metadata and source.metadata.get("published_date"):
            return str(source.metadata["published_date"])
        return None

    def _derive_key_concepts(self, state: ResearcherState) -> list[str]:
        """
        Derive key concepts primarily from evidence tags, with planner/research-task
        inclusions as fallback support.
        """
        ordered_concepts: list[str] = []
        seen: set[str] = set()

        for evidence_item in state.evidence_items:
            for tag in evidence_item.tags:
                cleaned = self._clean_text(tag)
                if not cleaned:
                    continue

                key = cleaned.casefold()
                if key in seen:
                    continue

                seen.add(key)
                ordered_concepts.append(cleaned)

        if state.research_task is not None:
            for concept in state.research_task.scope_inclusions:
                cleaned = self._clean_text(concept)
                if not cleaned:
                    continue

                key = cleaned.casefold()
                if key in seen:
                    continue

                seen.add(key)
                ordered_concepts.append(cleaned)

        return ordered_concepts

    def _derive_open_questions(self, state: ResearcherState) -> list[str]:
        """
        Build open questions from coverage gaps and unresolved research questions.
        """
        open_questions: list[str] = []
        seen: set[str] = set()

        if state.coverage_report is not None:
            for topic in state.coverage_report.missing_topics:
                cleaned = self._clean_text(topic)
                if not cleaned:
                    continue

                key = cleaned.casefold()
                if key in seen:
                    continue

                seen.add(key)
                open_questions.append(cleaned)

        if (
            state.coverage_report is not None
            and state.coverage_report.weak_evidence_types
        ):
            for evidence_type in state.coverage_report.weak_evidence_types:
                question = (
                    f"Need stronger support for evidence type: {evidence_type.value}"
                )
                key = question.casefold()
                if key in seen:
                    continue

                seen.add(key)
                open_questions.append(question)

        if state.research_task is not None and state.coverage_report is not None:
            for question in state.research_task.research_questions:
                cleaned_question = self._clean_text(question)
                if not cleaned_question:
                    continue

                if self._question_looks_unresolved(
                    question=cleaned_question,
                    state=state,
                ):
                    key = cleaned_question.casefold()
                    if key in seen:
                        continue

                    seen.add(key)
                    open_questions.append(cleaned_question)

        return open_questions

    def _build_writing_guidance(self, state: ResearcherState) -> list[str]:
        """
        Produce concise handoff guidance for the Notes Synthesizer / Writer layers.
        This is not prose generation.
        """
        guidance: list[str] = []

        if state.research_task is not None:
            guidance.append(
                f"Stay focused on the section objective: {state.research_task.objective}"
            )

            if state.research_task.scope_exclusions:
                exclusions = ", ".join(
                    self._clean_text(item)
                    for item in state.research_task.scope_exclusions
                    if self._clean_text(item)
                )
                if exclusions:
                    guidance.append(f"Avoid drifting into: {exclusions}")

        if state.coverage_report is not None:
            if state.coverage_report.missing_topics:
                missing = ", ".join(
                    self._clean_text(item)
                    for item in state.coverage_report.missing_topics
                    if self._clean_text(item)
                )
                if missing:
                    guidance.append(f"Handle remaining weak areas carefully: {missing}")

            if state.coverage_report.weak_evidence_types:
                weak_types = ", ".join(
                    evidence_type.value
                    for evidence_type in state.coverage_report.weak_evidence_types
                )
                if weak_types:
                    guidance.append(
                        f"Be careful where support is thinner: {weak_types}"
                    )

        evidence_type_counts = self._count_evidence_types(state)
        if evidence_type_counts:
            sorted_types = sorted(
                evidence_type_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
            strongest_types = ", ".join(
                f"{evidence_type} ({count})"
                for evidence_type, count in sorted_types[:3]
            )
            guidance.append(
                f"Lean on the strongest available evidence categories: {strongest_types}"
            )

        if state.reflexion_decision is not None:
            guidance.append(
                f"Research finalization note: {self._clean_text(state.reflexion_decision.reasoning)}"
            )

        return self._clean_list(guidance)

    def _question_looks_unresolved(
        self,
        *,
        question: str,
        state: ResearcherState,
    ) -> bool:
        """
        Very simple heuristic:
        if the question does not appear to be reflected in evidence content,
        tags, or summaries, treat it as still open.
        """
        question_terms = {
            token.casefold() for token in question.split() if len(token.strip()) >= 4
        }

        if not question_terms:
            return False

        searchable_blobs: list[str] = []
        for item in state.evidence_items:
            searchable_blobs.append(item.content)
            if item.summary:
                searchable_blobs.append(item.summary)
            if item.relevance_note:
                searchable_blobs.append(item.relevance_note)
            if item.tags:
                searchable_blobs.append(" ".join(item.tags))

        combined = " ".join(searchable_blobs).casefold()
        matched_terms = sum(1 for term in question_terms if term in combined)

        return matched_terms == 0

    def _count_evidence_types(self, state: ResearcherState) -> dict[str, int]:
        """
        Count evidence items by evidence type.
        """
        counts: dict[str, int] = {}
        for item in state.evidence_items:
            key = item.evidence_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _clean_text(self, value: str) -> str:
        """
        Normalize text consistently.
        """
        return " ".join(value.split()).strip()

    def _clean_list(self, values: list[str]) -> list[str]:
        """
        Normalize, drop empties, and deduplicate while preserving order.
        """
        cleaned_values: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = self._clean_text(value)
            if not cleaned:
                continue

            key = cleaned.casefold()
            if key in seen:
                continue

            seen.add(key)
            cleaned_values.append(cleaned)

        return cleaned_values
