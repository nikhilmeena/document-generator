"""Generate project documents and bundle as ZIP."""

from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

from brs_parser import extract_document_name, extract_for_review, purpose_sections_from_edit
from generators.docx_generator import (
    generate_approach_document,
    generate_impact_document,
    generate_uat_deployment_note,
)
from generators.system_test_cases import generate_system_test_cases
from models.project_context import ProjectContext
from ods_updater import generate_from_template

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "template_data"

DOCUMENT_TYPES = {
    "approach": {
        "label": "Approach Document",
        "template": "Approch document.docx",
        "filename": "Approach_Document.docx",
    },
    "impact": {
        "label": "Impact Document",
        "template": "Impact document.docx",
        "filename": "Impact_Document.docx",
    },
    "system_test_cases": {
        "label": "System Test Cases",
        "template": "System_Test_cases.xlsx",
        "filename": "System_Test_Cases.xlsx",
        "requires_testcase": True,
    },
    "uat_deployment": {
        "label": "UAT Deployment Note",
        "template": "UAT_DeploymentNote.docx",
        "filename": "UAT_Deployment_Note.docx",
    },
    "release_deployment": {
        "label": "Release Deployment iMobile",
        "template": "Release_Deployment_IMobile.ods",
        "filename": "Release_Deployment_IMobile.ods",
    },
}


def build_context(
    brs_path: Path,
    cr_number: str,
    deployment_date: str,
    files_components: str,
    spoc_name: str,
    comments: str = "",
    section_1_1: str | None = None,
    section_1_3: str | None = None,
    section_2_1: str | None = None,
    document_name: str | None = None,
) -> ProjectContext:
    extracted_name = extract_document_name(brs_path)
    if document_name is None:
        document_name = extracted_name
    if not document_name:
        raise ValueError("Document name is required.")

    if section_1_1 is not None and section_1_3 is not None and section_2_1 is not None:
        purpose_sections = purpose_sections_from_edit(section_1_1, section_1_3, section_2_1)
    else:
        raise ValueError("BRS sections 1.1, 1.3, and 2.1 are required.")

    return ProjectContext(
        cr_number=cr_number,
        deployment_date=deployment_date,
        files_components=files_components,
        spoc_name=spoc_name,
        document_name=document_name,
        purpose_sections=purpose_sections,
        comments=comments,
    )


def extract_review_data(brs_path: Path) -> dict:
    extraction = extract_for_review(brs_path)
    return {
        "document_name": extraction.document_name,
        "is_structured": extraction.is_structured,
        "raw_content": extraction.raw_content,
        "sections": extraction.sections,
    }


def generate_documents(
    brs_path: Path,
    context: ProjectContext,
    selected: set[str],
    testcase_path: Path | None = None,
) -> list[tuple[str, Path]]:
    outputs: list[tuple[str, Path]] = []

    for doc_type in selected:
        if doc_type not in DOCUMENT_TYPES:
            raise ValueError(f"Unknown document type: {doc_type}")

        meta = DOCUMENT_TYPES[doc_type]
        template_path = TEMPLATE_DIR / meta["template"]
        if not template_path.exists():
            raise ValueError(f"Missing template: {meta['template']}")

        if meta.get("requires_testcase") and testcase_path is None:
            raise ValueError(
                "System Test Cases requires an uploaded test case workbook."
            )

        if doc_type == "approach":
            path = generate_approach_document(template_path, context)
        elif doc_type == "impact":
            path = generate_impact_document(template_path, context)
        elif doc_type == "system_test_cases":
            path = generate_system_test_cases(template_path, testcase_path, context)
        elif doc_type == "uat_deployment":
            path = generate_uat_deployment_note(template_path, context)
        elif doc_type == "release_deployment":
            path = generate_from_template(
                template_path=template_path,
                cr_number=context.cr_number,
                deployment_date=context.deployment_date,
                purpose_sections=context.purpose_sections,
                cr_description=context.document_name,
                files_components=context.files_components,
            )
        else:
            continue

        outputs.append((meta["filename"], path))

    return outputs


def create_zip_bundle(files: list[tuple[str, Path]], cr_number: str) -> Path:
    with NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
        zip_path = Path(temp_file.name)

    safe_cr = cr_number.replace("/", "-")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, path in files:
            archive.write(path, arcname=f"{safe_cr}/{filename}")

    return zip_path
