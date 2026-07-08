from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

from planner_agent.schemas import BookPlan
from researcher.schemas import PlannerSectionRef, SectionResearchPacket
from researcher.state import ResearcherState
from researcher.workflow import ResearcherWorkflow


def _research_concurrency() -> int:
    for name in ("WRITERLM_RESEARCH_CONCURRENCY", "RESEARCH_CONCURRENCY"):
        value = os.getenv(name)
        if value and value.strip():
            try:
                parsed = int(value)
            except ValueError:
                continue
            if parsed > 0:
                return parsed
    return 4


class ChapterResearchBundle(BaseModel):
    chapter_id: str
    chapter_title: str
    section_packets: list[SectionResearchPacket] = Field(default_factory=list)


class BookResearchBundle(BaseModel):
    book_plan: BookPlan
    chapters: list[ChapterResearchBundle] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PlannerResearchPipeline:
    """
    Connect the Planner and Researcher layers.

    Responsibilities:
    - run the planner workflow
    - iterate through the planner's chapters and sections
    - convert planner sections into Researcher-compatible PlannerSectionRef objects
    - run the Researcher workflow per section
    - collect and group section research packets by chapter
    - return one combined book-level research bundle
    """

    def __init__(
        self,
        *,
        planner_workflow,
        researcher_workflow: ResearcherWorkflow,
    ) -> None:
        self.planner_workflow = planner_workflow
        self.researcher_workflow = researcher_workflow

    def run(self, planner_input) -> BookResearchBundle:
        """
        Execute planner first, then researcher per section, and return
        one combined bundle for the next layer.
        """
        book_plan = self.planner_workflow.run(planner_input)
        return self.run_from_book_plan(book_plan)

    def run_from_book_plan(self, book_plan: BookPlan) -> BookResearchBundle:
        """
        Execute only the researcher against an existing planner-produced book plan.

        This is used by web job retry/resume flows when book_plan.json exists but
        research_bundle.json does not.
        """
        all_chapter_bundles: list[ChapterResearchBundle] = []
        all_warnings: list[str] = []
        all_errors: list[str] = []

        # Flatten sections so research runs in parallel across the whole book,
        # then regroup results in original order.
        jobs = [
            (chapter, section)
            for chapter in book_plan.chapters
            for section in chapter.sections
        ]
        max_workers = max(1, _research_concurrency())

        def research_one(job):
            chapter, section = job
            planner_section = self._build_planner_section_ref(
                chapter=chapter,
                section=section,
            )
            state = ResearcherState(planner_section=planner_section)
            try:
                return self.researcher_workflow.run(state)
            except Exception as exc:
                failed_state = ResearcherState(planner_section=planner_section)
                failed_state.errors.append(f"Researcher workflow raised: {exc}")
                return failed_state

        if max_workers == 1 or len(jobs) <= 1:
            final_states = [research_one(job) for job in jobs]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                final_states = list(executor.map(research_one, jobs))

        # jobs was built in chapter/section order, so results align positionally.
        state_iter = iter(final_states)

        for chapter in book_plan.chapters:
            chapter_packets: list[SectionResearchPacket] = []

            for section in chapter.sections:
                final_state = next(state_iter)

                all_warnings.extend(
                    self._prefix_messages(
                        messages=final_state.warnings,
                        chapter_title=chapter.title,
                        section_title=section.title,
                        level="warning",
                    )
                )
                all_errors.extend(
                    self._prefix_messages(
                        messages=final_state.errors,
                        chapter_title=chapter.title,
                        section_title=section.title,
                        level="error",
                    )
                )

                if final_state.research_packet is not None:
                    chapter_packets.append(final_state.research_packet)
                else:
                    all_errors.append(
                        self._format_missing_packet_message(
                            chapter_title=chapter.title,
                            section_title=section.title,
                        )
                    )

            all_chapter_bundles.append(
                ChapterResearchBundle(
                    chapter_id=self._build_chapter_id(
                        chapter_number=chapter.chapter_number,
                        chapter_title=chapter.title,
                    ),
                    chapter_title=chapter.title,
                    section_packets=chapter_packets,
                )
            )

        return BookResearchBundle(
            book_plan=book_plan,
            chapters=all_chapter_bundles,
            warnings=all_warnings,
            errors=all_errors,
        )

    def _build_planner_section_ref(
        self,
        *,
        chapter,
        section,
    ) -> PlannerSectionRef:
        """
        Adapt planner output objects into the Researcher layer's section input model.

        This method assumes the planner has chapter/section objects with common fields.
        If your planner schema uses different field names, adjust this adapter only.
        """
        return PlannerSectionRef(
            section_id=self._build_section_id(
                chapter_number=chapter.chapter_number,
                section_title=section.title,
            ),
            chapter_id=self._build_chapter_id(
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.title,
            ),
            chapter_title=chapter.title,
            section_title=section.title,
            section_goal=section.goal,
            section_summary=getattr(section, "summary", None),
            key_points=getattr(section, "key_points", []),
        )

    def _build_chapter_id(self, *, chapter_number: int, chapter_title: str) -> str:
        slug = self._slugify(chapter_title)
        return f"chapter-{chapter_number}-{slug}"

    def _build_section_id(self, *, chapter_number: int, section_title: str) -> str:
        slug = self._slugify(section_title)
        return f"chapter-{chapter_number}-section-{slug}"

    def _slugify(self, value: str) -> str:
        cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
        slug = "-".join(part for part in cleaned.split("-") if part)
        return slug or "untitled"

    def _prefix_messages(
        self,
        *,
        messages: list[str],
        chapter_title: str,
        section_title: str,
        level: str,
    ) -> list[str]:
        """
        Add chapter/section context to workflow warnings and errors.
        """
        prefixed: list[str] = []

        for message in messages:
            cleaned = " ".join(message.split()).strip()
            if not cleaned:
                continue

            prefixed.append(
                f"[{level}] Chapter='{chapter_title}' Section='{section_title}': {cleaned}"
            )

        return prefixed

    def _format_missing_packet_message(
        self,
        *,
        chapter_title: str,
        section_title: str,
    ) -> str:
        """
        Build a clear error message when a section fails to produce a final packet.
        """
        return (
            f"[error] Chapter='{chapter_title}' Section='{section_title}': "
            "Researcher workflow completed without producing a research packet."
        )
