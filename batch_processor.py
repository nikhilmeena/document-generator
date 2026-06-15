"""Scan CR folders, extract BRS/test cases, and batch-generate documents."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from brs_parser import extract_for_review
from generators import build_context, create_zip_bundle, generate_documents
from generators.system_test_cases import TESTCASE_FILENAME_PREFIX, extract_testcase_preview

SKIP_DOCX = {
    "approch document.docx",
    "impact document.docx",
    "uat_deploymentnote.docx",
}
CR_FOLDER_PATTERN = re.compile(r"^CR-\d+-\d+$", re.IGNORECASE)


@dataclass
class BatchFolderResult:
    folder_path: str
    folder_name: str
    cr_number: str
    brs_file: str
    brs_path: str
    testcase_file: str
    testcase_path: str
    testcase_sheet: str
    testcase_headers: list[str]
    testcase_rows: list[list[str]]
    testcase_row_count: int
    document_name: str
    is_structured: bool
    raw_content: str
    sections: dict[str, str] = field(default_factory=dict)
    testcase_error: str = ""
    error: str = ""


def safe_parent_path(path: str, allowed_root: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    root = allowed_root.expanduser().resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"Path must be inside {root}.")
    if not resolved.is_dir():
        raise ValueError("Parent folder not found.")
    return resolved


def list_batch_folders(parent: Path) -> list[Path]:
    folders = [
        item
        for item in sorted(parent.iterdir())
        if item.is_dir() and not item.name.startswith(".")
    ]
    cr_folders = [item for item in folders if CR_FOLDER_PATTERN.match(item.name)]
    return cr_folders or folders


def find_brs_file(folder: Path) -> Path | None:
    candidates = [
        item
        for item in folder.iterdir()
        if item.is_file()
        and item.suffix.lower() == ".docx"
        and item.name.lower() not in SKIP_DOCX
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    for item in candidates:
        if "brs" in item.name.lower():
            return item
    return candidates[0]


def find_testcase_file(folder: Path) -> Path | None:
    matches = [
        item
        for item in folder.iterdir()
        if item.is_file()
        and item.suffix.lower() in {".xlsx", ".xlsm"}
        and item.name.lower().startswith(TESTCASE_FILENAME_PREFIX)
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: item.name.lower())[0]


def _empty_testcase_fields() -> dict[str, object]:
    return {
        "testcase_sheet": "",
        "testcase_headers": [],
        "testcase_rows": [],
        "testcase_row_count": 0,
    }


def _testcase_fields_for_file(testcase: Path | None) -> dict[str, object]:
    if testcase is None:
        return _empty_testcase_fields()

    try:
        preview = extract_testcase_preview(testcase)
    except Exception as error:
        return {
            "testcase_sheet": "",
            "testcase_headers": [],
            "testcase_rows": [],
            "testcase_row_count": 0,
            "testcase_error": str(error),
        }

    fields = {
        "testcase_sheet": str(preview["sheet_name"]),
        "testcase_headers": list(preview["headers"]),
        "testcase_rows": list(preview["rows"]),
        "testcase_row_count": int(preview["total_rows"]),
    }
    return fields


def scan_folder(folder: Path) -> BatchFolderResult:
    folder = folder.resolve()
    brs = find_brs_file(folder)
    testcase = find_testcase_file(folder)
    testcase_fields = _testcase_fields_for_file(testcase)
    testcase_error = testcase_fields.pop("testcase_error", "")

    if not brs:
        return BatchFolderResult(
            folder_path=str(folder),
            folder_name=folder.name,
            cr_number=folder.name,
            brs_file="",
            brs_path="",
            testcase_file=testcase.name if testcase else "",
            testcase_path=str(testcase) if testcase else "",
            testcase_sheet=str(testcase_fields["testcase_sheet"]),
            testcase_headers=list(testcase_fields["testcase_headers"]),
            testcase_rows=list(testcase_fields["testcase_rows"]),
            testcase_row_count=int(testcase_fields["testcase_row_count"]),
            document_name="",
            is_structured=False,
            raw_content="",
            testcase_error=str(testcase_error),
            error="No BRS document found in folder.",
        )

    try:
        review = extract_for_review(brs)
    except Exception as error:
        return BatchFolderResult(
            folder_path=str(folder),
            folder_name=folder.name,
            cr_number=folder.name,
            brs_file=brs.name,
            brs_path=str(brs),
            testcase_file=testcase.name if testcase else "",
            testcase_path=str(testcase) if testcase else "",
            testcase_sheet=str(testcase_fields["testcase_sheet"]),
            testcase_headers=list(testcase_fields["testcase_headers"]),
            testcase_rows=list(testcase_fields["testcase_rows"]),
            testcase_row_count=int(testcase_fields["testcase_row_count"]),
            document_name="",
            is_structured=False,
            raw_content="",
            testcase_error=str(testcase_error),
            error=f"Failed to read BRS: {error}",
        )

    return BatchFolderResult(
        folder_path=str(folder),
        folder_name=folder.name,
        cr_number=folder.name,
        brs_file=brs.name,
        brs_path=str(brs),
        testcase_file=testcase.name if testcase else "",
        testcase_path=str(testcase) if testcase else "",
        testcase_sheet=str(testcase_fields["testcase_sheet"]),
        testcase_headers=list(testcase_fields["testcase_headers"]),
        testcase_rows=list(testcase_fields["testcase_rows"]),
        testcase_row_count=int(testcase_fields["testcase_row_count"]),
        document_name=review.document_name,
        is_structured=review.is_structured,
        raw_content=review.raw_content,
        sections=dict(review.sections),
        testcase_error=str(testcase_error),
    )


def scan_folders(parent: Path, selected_names: list[str] | None = None) -> list[BatchFolderResult]:
    folders = list_batch_folders(parent)
    if selected_names:
        selected = set(selected_names)
        folders = [folder for folder in folders if folder.name in selected]

    return [scan_folder(folder) for folder in folders]


def generate_folder_documents(
    item: BatchFolderResult,
    selected_documents: set[str],
    deployment_date: str,
    files_components: str,
    spoc_name: str,
    comments: str,
    section_1_1: str,
    section_1_3: str,
    section_2_1: str,
    document_name: str,
) -> Path:
    if item.error:
        raise ValueError(f"{item.folder_name}: {item.error}")
    if not section_1_1 or not section_1_3 or not section_2_1:
        raise ValueError(f"{item.folder_name}: BRS sections 1.1, 1.3, and 2.1 are required.")
    if not document_name:
        raise ValueError(f"{item.folder_name}: Document name is required.")

    brs_path = Path(item.brs_path)
    testcase_path = Path(item.testcase_path) if item.testcase_path else None
    context = build_context(
        brs_path=brs_path,
        cr_number=item.cr_number,
        deployment_date=deployment_date,
        files_components=files_components,
        spoc_name=spoc_name,
        comments=comments,
        section_1_1=section_1_1,
        section_1_3=section_1_3,
        section_2_1=section_2_1,
        document_name=document_name,
    )
    outputs = generate_documents(
        brs_path=brs_path,
        context=context,
        selected=selected_documents,
        testcase_path=testcase_path,
    )
    return create_zip_bundle(outputs, item.cr_number)


def write_zip_to_folder(zip_path: Path, folder: Path, cr_number: str) -> Path:
    safe_cr = cr_number.replace("/", "-")
    destination = folder / f"Project_Documents_{safe_cr}.zip"
    shutil.copy2(zip_path, destination)
    return destination
