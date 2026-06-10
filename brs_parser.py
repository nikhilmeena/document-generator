"""Extract purpose-of-deployment content from a BRS Word document."""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SECTION_PATTERN = re.compile(r"^(\d+\.\d+)\s+(.+)$")
TARGET_SECTIONS = ("1.1", "1.3", "2.1")
PLACEHOLDER_PATTERN = re.compile(r"^<.*updated.*>$", re.IGNORECASE)
DOC_BULLET_PATTERN = re.compile(r"^[\u2022\u25CF\u25E6\u2043\u2219\u00B7•●○◦\-–—]\s+")


@dataclass
class PurposeSection:
    number: int
    title: str
    lines: list[str]


class ParagraphInfo:
    __slots__ = ("text", "is_list_item")

    def __init__(self, text: str, is_list_item: bool = False) -> None:
        self.text = text
        self.is_list_item = is_list_item


def _paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for text_node in paragraph.iter(f"{W_NS}t"):
        if text_node.text:
            parts.append(text_node.text)
        if text_node.tail:
            parts.append(text_node.tail)
    return "".join(parts)


def _is_list_paragraph(paragraph: ET.Element) -> bool:
    return paragraph.find(f".//{W_NS}numPr") is not None


def _extract_paragraphs(docx_path: str | Path) -> list[ParagraphInfo]:
    with zipfile.ZipFile(docx_path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    paragraphs: list[ParagraphInfo] = []

    for paragraph in root.iter(f"{W_NS}p"):
        text = _paragraph_text(paragraph)
        if text:
            paragraphs.append(ParagraphInfo(text, _is_list_paragraph(paragraph)))

    return paragraphs


def _is_toc_line(text: str) -> bool:
    """Table-of-contents entries often end with a page number."""
    return bool(re.search(r"\d+$", text.strip())) and re.match(
        r"^\d+(\.\d+)*\s", text.strip()
    )


def _clean_section_title(title: str) -> str:
    return title.rstrip("*").strip()


def _is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.match(text.strip()))


def _strip_doc_bullet_prefix(text: str) -> str:
    return DOC_BULLET_PATTERN.sub("", text.strip()).strip()


def _format_section_lines(lines: list[ParagraphInfo]) -> list[str]:
    formatted: list[str] = []
    list_counter = 0

    for paragraph in lines:
        text = _strip_doc_bullet_prefix(paragraph.text.strip())
        if not text:
            continue

        if paragraph.is_list_item:
            list_counter += 1
            formatted.append(f"{list_counter}. {text}")
            continue

        list_counter = 0
        formatted.append(text)

    return formatted


def _parse_target_sections(
    paragraphs: list[ParagraphInfo],
) -> dict[str, dict[str, object]]:
    sections: dict[str, dict[str, object]] = {
        section: {"title": "", "lines": []} for section in TARGET_SECTIONS
    }
    current_section: str | None = None

    for paragraph in paragraphs:
        stripped = paragraph.text.strip()
        if not stripped or _is_toc_line(stripped):
            continue

        match = SECTION_PATTERN.match(stripped)
        if match:
            section_number, section_title = match.groups()
            if section_number in TARGET_SECTIONS:
                current_section = section_number
                sections[section_number]["title"] = _clean_section_title(section_title)
            else:
                current_section = None
            continue

        if current_section and not _is_placeholder(stripped):
            sections[current_section]["lines"].append(paragraph)

    return sections


def _sections_are_complete(sections: dict[str, dict[str, object]]) -> bool:
    return all(sections[section]["lines"] for section in TARGET_SECTIONS)


def _purpose_sections_from_parsed(
    sections: dict[str, dict[str, object]],
) -> list[PurposeSection]:
    purpose_sections: list[PurposeSection] = []
    for index, section_number in enumerate(TARGET_SECTIONS, start=1):
        parsed = sections[section_number]
        lines: list[ParagraphInfo] = parsed["lines"]
        title = parsed["title"]
        if not lines:
            continue

        purpose_sections.append(
            PurposeSection(
                number=index,
                title=title,
                lines=_format_section_lines(lines),
            )
        )
    return purpose_sections


def _find_section_bounds(
    paragraphs: list[ParagraphInfo],
    start_pattern: str,
    end_pattern: str | None = None,
) -> tuple[int, int] | None:
    start = None
    end = len(paragraphs)

    for index, paragraph in enumerate(paragraphs):
        stripped = paragraph.text.strip()
        if start is None and re.match(start_pattern, stripped, re.IGNORECASE):
            start = index
            continue
        if start is not None and end_pattern and re.match(end_pattern, stripped, re.IGNORECASE):
            end = index
            break

    if start is None:
        return None
    return start, end


def _paragraphs_to_text(paragraphs: list[ParagraphInfo]) -> str:
    lines: list[str] = []
    for paragraph in paragraphs:
        text = _strip_doc_bullet_prefix(paragraph.text.strip())
        if not text or _is_placeholder(text) or _is_toc_line(text):
            continue
        if paragraph.is_list_item:
            lines.append(f"• {text}")
        else:
            lines.append(text)
    return "\n".join(lines).strip()


def extract_raw_brs_content(docx_path: str | Path) -> str:
    """Extract readable BRS content when standard sections are missing."""
    paragraphs = _extract_paragraphs(docx_path)
    blocks: list[str] = []

    intro_bounds = _find_section_bounds(
        paragraphs,
        r"^1\.?\s*Introduction",
        r"^2\.?\s*Requirement Description",
    )
    if intro_bounds:
        start, end = intro_bounds
        intro_text = _paragraphs_to_text(paragraphs[start:end])
        if intro_text:
            blocks.append(
                "=== Introduction and High-Level Requirement ===\n" + intro_text
            )

    req_bounds = _find_section_bounds(
        paragraphs,
        r"^2\.?\s*Requirement Description",
        r"^3\.?\s+",
    )
    if req_bounds:
        start, end = req_bounds
        req_text = _paragraphs_to_text(paragraphs[start:end])
        if req_text:
            blocks.append("=== Requirement Description ===\n" + req_text)

    if blocks:
        return "\n\n".join(blocks).strip()

    skip_prefixes = (
        "business requirement document",
        "document name:",
        "created by:",
        "created date:",
        "guidelines:",
        "table of contents",
    )
    loose_lines: list[str] = []
    for paragraph in paragraphs:
        stripped = paragraph.text.strip()
        if not stripped or _is_toc_line(stripped):
            continue
        lower = stripped.lower()
        if any(lower.startswith(prefix) for prefix in skip_prefixes):
            continue
        if re.match(r"^revision history", lower):
            break
        text = _strip_doc_bullet_prefix(stripped)
        if text and not _is_placeholder(text):
            loose_lines.append(text)

    return "\n".join(loose_lines[:80]).strip()


@dataclass
class ReviewExtraction:
    document_name: str
    is_structured: bool
    raw_content: str
    sections: dict[str, str]


def extract_for_review(docx_path: str | Path) -> ReviewExtraction:
    """Extract BRS data for the review screen."""
    paragraphs = _extract_paragraphs(docx_path)
    document_name = extract_document_name(docx_path)
    if not document_name:
        for paragraph in paragraphs[:20]:
            stripped = paragraph.text.strip()
            if stripped and len(stripped) > 10 and not _is_toc_line(stripped):
                if not re.match(
                    r"^(business requirement|created by|created date|guidelines)",
                    stripped,
                    re.IGNORECASE,
                ):
                    document_name = stripped[:200]
                    break
    if not document_name:
        document_name = Path(docx_path).stem.replace("_", " ")

    parsed = _parse_target_sections(paragraphs)
    if _sections_are_complete(parsed):
        purpose_sections = _purpose_sections_from_parsed(parsed)
        return ReviewExtraction(
            document_name=document_name,
            is_structured=True,
            raw_content="",
            sections=format_sections_for_review(purpose_sections),
        )

    return ReviewExtraction(
        document_name=document_name,
        is_structured=False,
        raw_content=extract_raw_brs_content(docx_path),
        sections={"1.1": "", "1.3": "", "2.1": ""},
    )


def extract_purpose_sections(docx_path: str | Path) -> list[PurposeSection]:
    """Extract sections 1.1, 1.3, and 2.1 as numbered purpose blocks."""
    paragraphs = _extract_paragraphs(docx_path)
    parsed = _parse_target_sections(paragraphs)
    purpose_sections = _purpose_sections_from_parsed(parsed)

    if not purpose_sections:
        raise ValueError(
            "Could not find sections 1.1, 1.3, and 2.1 in the BRS document."
        )

    return purpose_sections


def extract_purpose_text(docx_path: str | Path) -> str:
    """Plain-text preview of numbered purpose sections."""
    blocks: list[str] = []
    for section in extract_purpose_sections(docx_path):
        blocks.append(f"{section.number}. {section.title}")
        blocks.extend(section.lines)
        blocks.append("")
    return "\n".join(blocks).strip()


def extract_introduction(docx_path: str | Path) -> str:
    """Backward-compatible alias for purpose text extraction."""
    return extract_purpose_text(docx_path)


def extract_document_name(docx_path: str | Path) -> str | None:
    paragraphs = _extract_paragraphs(docx_path)
    for paragraph in paragraphs[:10]:
        match = re.match(r"Document Name:\s*(.+)", paragraph.text.strip(), re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def format_section_edit(section: PurposeSection, brs_number: str) -> str:
    """Format a BRS section for display in the review UI."""
    lines = [f"{brs_number} {section.title}", ""] + section.lines
    return "\n".join(lines).strip()


def format_sections_for_review(sections: list[PurposeSection]) -> dict[str, str]:
    """Return editable text blocks keyed by BRS section number."""
    brs_numbers = ("1.1", "1.3", "2.1")
    result: dict[str, str] = {}
    for brs_number, section in zip(brs_numbers, sections):
        result[brs_number] = format_section_edit(section, brs_number)
    return result


def parse_edited_section(text: str, number: int) -> PurposeSection:
    """Parse user-edited section text back into a PurposeSection."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)

    title = ""
    content_start = 0
    if lines:
        title_line = lines[0].strip()
        title = re.sub(r"^\d+(?:\.\d+)?\s*", "", title_line).strip()
        content_start = 1

    content_lines = [line for line in lines[content_start:] if line.strip()]
    return PurposeSection(number=number, title=title, lines=content_lines)


def purpose_sections_from_edit(
    section_1_1: str,
    section_1_3: str,
    section_2_1: str,
) -> list[PurposeSection]:
    return [
        parse_edited_section(section_1_1, 1),
        parse_edited_section(section_1_3, 2),
        parse_edited_section(section_2_1, 3),
    ]
