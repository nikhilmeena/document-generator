"""Update Release Deployment ODS files with CR, date, and purpose text."""

from __future__ import annotations

import re
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile

from odf import teletype
from odf.namespaces import OFFICENS
from odf.opendocument import load
from odf.style import Style, TextProperties
from odf.table import Table, TableRow, TableCell
from odf.text import P, Span

from brs_parser import PurposeSection


def _set_cell_text(cell: TableCell, text: str) -> None:
    for paragraph in cell.getElementsByType(P):
        cell.removeChild(paragraph)
    cell.addElement(P(text=text))


def _get_bold_style(document) -> Style:
    style_name = "PurposeTitleBold"
    for style in document.automaticstyles.getElementsByType(Style):
        if style.getAttribute("name") == style_name:
            return style

    style = Style(name=style_name, family="text")
    style.addElement(TextProperties(fontweight="bold"))
    document.automaticstyles.addElement(style)
    return style


def _set_cell_purpose(cell: TableCell, sections: list[PurposeSection], document) -> None:
    for paragraph in cell.getElementsByType(P):
        cell.removeChild(paragraph)

    bold_style = _get_bold_style(document)

    for index, section in enumerate(sections):
        if index > 0:
            cell.addElement(P())

        header = P()
        header.addText(f"{section.number}. ")
        header.addElement(Span(stylename=bold_style, text=section.title))
        cell.addElement(header)
        cell.addElement(P())

        for line in section.lines:
            cell.addElement(P(text=line))


def _to_iso_date(deployment_date: str) -> str:
    """Convert DD-MM-YYYY (or YYYY-MM-DD) to an ODF date-value."""
    deployment_date = deployment_date.strip()
    match = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", deployment_date)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}T00:00:00"

    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", deployment_date)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}T00:00:00"

    raise ValueError(
        "Deployment date must be in DD-MM-YYYY format (example: 18-05-2026)."
    )


def _set_cell_date(cell: TableCell, text: str) -> None:
    _set_cell_text(cell, text.strip())
    cell.attributes[(OFFICENS, "value-type")] = "date"
    cell.attributes[(OFFICENS, "date-value")] = _to_iso_date(text)


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip()


def _row_label(cells: list[TableCell]) -> str:
    if not cells:
        return ""
    return _normalize_label(teletype.extractText(cells[0]))


def update_release_deployment(
    template_path: str | Path,
    output_path: str | Path,
    cr_number: str,
    deployment_date: str,
    purpose_sections: list[PurposeSection],
    cr_description: str | None = None,
    files_components: str | None = None,
) -> None:
    document = load(str(template_path))
    updated = False

    for table in document.getElementsByType(Table):
        for row in table.getElementsByType(TableRow):
            cells = row.getElementsByType(TableCell)
            if not cells:
                continue

            label = _row_label(cells)

            if label == "Date:":
                _set_cell_date(cells[1], deployment_date)
                updated = True
            elif label == "CR No.":
                _set_cell_text(cells[1], cr_number.strip())
                if len(cells) > 2 and cr_description:
                    _set_cell_text(cells[2], cr_description.strip())
                updated = True
            elif label.startswith("Purpose of the Deployment"):
                _set_cell_purpose(cells[1], purpose_sections, document)
                if len(cells) > 2:
                    _set_cell_text(cells[2], "")
                updated = True
            elif label.startswith(
                "Number of files/Components being moved as part of this CR/Project:"
            ):
                _set_cell_text(cells[1], files_components.strip())
                updated = True

    if not updated:
        raise ValueError(
            "Could not find required rows in the release deployment template."
        )

    document.save(str(output_path))


def generate_from_template(
    template_path: str | Path,
    cr_number: str,
    deployment_date: str,
    purpose_sections: list[PurposeSection],
    cr_description: str | None = None,
    files_components: str | None = None,
) -> Path:
    with NamedTemporaryFile(delete=False, suffix=".ods") as temp_file:
        output_path = Path(temp_file.name)

    copyfile(template_path, output_path)
    update_release_deployment(
        template_path=output_path,
        output_path=output_path,
        cr_number=cr_number,
        deployment_date=deployment_date,
        purpose_sections=purpose_sections,
        cr_description=cr_description,
        files_components=files_components,
    )
    return output_path
