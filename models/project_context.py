"""Shared project data for document generation."""

from __future__ import annotations

from dataclasses import dataclass

from brs_parser import PurposeSection


@dataclass
class ProjectContext:
    cr_number: str
    deployment_date: str
    files_components: str
    spoc_name: str
    document_name: str
    purpose_sections: list[PurposeSection]
    comments: str = ""

    def section_text(self, index: int) -> str:
        if index >= len(self.purpose_sections):
            return ""
        return "\n".join(self.purpose_sections[index].lines)

    def numbered_section_block(self, index: int, display_number: int | None = None) -> str:
        """Plain-text block: '1. Title' plus content (for fallback)."""
        if index >= len(self.purpose_sections):
            return ""
        section = self.purpose_sections[index]
        number = display_number if display_number is not None else section.number
        lines = [f"{number}. {section.title}", ""] + section.lines
        return "\n".join(lines).strip()

    def introduction_sections(self) -> list[PurposeSection]:
        """Section 1.1 as numbered bullet 1."""
        if not self.purpose_sections:
            return []
        section = self.purpose_sections[0]
        return [PurposeSection(number=1, title=section.title, lines=section.lines)]

    def all_requirement_sections(self) -> list[PurposeSection]:
        """Sections 1.1, 1.3, 2.1 as numbered bullets 1, 2, 3."""
        numbered: list[PurposeSection] = []
        for index, section in enumerate(self.purpose_sections[:3]):
            numbered.append(
                PurposeSection(
                    number=index + 1,
                    title=section.title,
                    lines=section.lines,
                )
            )
        return numbered

    def uat_body_sections(self) -> list[list[PurposeSection]]:
        """UAT body fields in template order (1.3, 1.1, 2.1) as bullets 1, 2, 3."""
        order = (1, 0, 2)
        blocks: list[list[PurposeSection]] = []
        for display_number, section_index in enumerate(order, start=1):
            if section_index >= len(self.purpose_sections):
                blocks.append([])
                continue
            section = self.purpose_sections[section_index]
            blocks.append(
                [
                    PurposeSection(
                        number=display_number,
                        title=section.title,
                        lines=section.lines,
                    )
                ]
            )
        return blocks

    def section_summary(self, index: int) -> str:
        if index >= len(self.purpose_sections):
            return ""
        section = self.purpose_sections[index]
        if section.lines:
            return section.lines[0]
        return section.title

    def introduction_text(self) -> str:
        """Approach introduction: BRS 1.1 heading and paragraph(s)."""
        return self.numbered_section_block(0, display_number=1)

    def all_requirements_text(self) -> str:
        """Approach requirement 1: BRS 1.1, 1.3, and 2.1."""
        return "\n\n".join(
            self.numbered_section_block(index, display_number=index + 1)
            for index in range(min(3, len(self.purpose_sections)))
        )

    def deployment_title(self) -> str:
        """Short title for deployment note headers."""
        return self.document_name

    def uat_purpose_paragraphs(self) -> list[str]:
        """UAT template order: 1.3, 1.1, 2.1 body paragraphs."""
        order = (1, 0, 2)
        return [self.section_text(i) for i in order if i < len(self.purpose_sections)]

    def module_name(self) -> str:
        """Module/Unit tested label."""
        return self.document_name
