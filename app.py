"""Web app to generate project documents from BRS and test case uploads."""

import os
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from generators import (
    DOCUMENT_TYPES,
    build_context,
    create_zip_bundle,
    extract_review_data,
    generate_documents,
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_BRS_EXTENSIONS = {".docx"}
ALLOWED_TESTCASE_EXTENSIONS = {".xlsx", ".xlsm"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "release-deployment-dev-key")


def _allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    return Path(filename).suffix.lower() in allowed_extensions


def _safe_upload_path(filename: str) -> Path:
    path = (UPLOAD_DIR / secure_filename(filename)).resolve()
    if not str(path).startswith(str(UPLOAD_DIR.resolve())):
        raise ValueError("Invalid upload path.")
    if not path.exists():
        raise ValueError("Uploaded file not found. Please upload again.")
    return path


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", document_types=DOCUMENT_TYPES)


@app.route("/review", methods=["POST"])
def review():
    brs_file = request.files.get("brs_file")
    testcase_file = request.files.get("testcase_file")
    cr_number = request.form.get("cr_number", "").strip()
    deployment_date = request.form.get("deployment_date", "").strip()
    files_components = request.form.get("files_components", "").strip()
    spoc_name = request.form.get("spoc_name", "").strip() or "Nikhil"
    comments = request.form.get("comments", "").strip()
    selected = request.form.getlist("documents")

    if not brs_file or not brs_file.filename:
        flash("Please upload a BRS document (.docx).", "error")
        return redirect(url_for("index"))

    if not cr_number or not deployment_date or not files_components:
        flash("Please fill in CR number, deployment date, and files/components.", "error")
        return redirect(url_for("index"))

    if not selected:
        flash("Please select at least one document to generate.", "error")
        return redirect(url_for("index"))

    if not _allowed_file(brs_file.filename, ALLOWED_BRS_EXTENSIONS):
        flash("BRS file must be a .docx document.", "error")
        return redirect(url_for("index"))

    brs_name = secure_filename(brs_file.filename)
    brs_path = UPLOAD_DIR / brs_name
    brs_file.save(brs_path)

    testcase_name = ""
    if testcase_file and testcase_file.filename:
        if not _allowed_file(testcase_file.filename, ALLOWED_TESTCASE_EXTENSIONS):
            flash("Test case file must be an .xlsx workbook.", "error")
            return redirect(url_for("index"))
        testcase_name = secure_filename(testcase_file.filename)
        testcase_file.save(UPLOAD_DIR / testcase_name)

    if "system_test_cases" in selected and not testcase_name:
        flash("System Test Cases requires an uploaded test case workbook (.xlsx).", "error")
        return redirect(url_for("index"))

    try:
        review_data = extract_review_data(brs_path)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("index"))
    except Exception as error:
        flash(f"Failed to read BRS: {error}", "error")
        return redirect(url_for("index"))

    return render_template(
        "review.html",
        document_types=DOCUMENT_TYPES,
        document_name=review_data["document_name"],
        is_structured=review_data["is_structured"],
        raw_content=review_data["raw_content"],
        sections=review_data["sections"],
        brs_filename=brs_name,
        testcase_filename=testcase_name,
        cr_number=cr_number,
        deployment_date=deployment_date,
        files_components=files_components,
        spoc_name=spoc_name,
        comments=comments,
        selected_documents=selected,
    )


@app.route("/generate", methods=["POST"])
def generate():
    brs_filename = request.form.get("brs_filename", "").strip()
    testcase_filename = request.form.get("testcase_filename", "").strip()
    cr_number = request.form.get("cr_number", "").strip()
    deployment_date = request.form.get("deployment_date", "").strip()
    files_components = request.form.get("files_components", "").strip()
    spoc_name = request.form.get("spoc_name", "").strip() or "Nikhil"
    comments = request.form.get("comments", "").strip()
    selected = set(request.form.getlist("documents"))

    document_name = request.form.get("document_name", "").strip()
    section_1_1 = request.form.get("section_1_1", "").strip()
    section_1_3 = request.form.get("section_1_3", "").strip()
    section_2_1 = request.form.get("section_2_1", "").strip()

    if not brs_filename or not selected:
        flash("Missing upload session. Please start again.", "error")
        return redirect(url_for("index"))

    if not document_name:
        flash("Document name is required.", "error")
        return redirect(url_for("index"))

    if not section_1_1 or not section_1_3 or not section_2_1:
        flash("BRS sections 1.1, 1.3, and 2.1 are required.", "error")
        return redirect(url_for("index"))

    try:
        brs_path = _safe_upload_path(brs_filename)
        testcase_path = (
            _safe_upload_path(testcase_filename) if testcase_filename else None
        )
        context = build_context(
            brs_path=brs_path,
            cr_number=cr_number,
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
            selected=selected,
            testcase_path=testcase_path,
        )
        zip_path = create_zip_bundle(outputs, cr_number)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("index"))
    except Exception as error:
        flash(f"Failed to generate documents: {error}", "error")
        return redirect(url_for("index"))

    download_name = f"Project_Documents_{cr_number.replace('/', '-')}.zip"
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/zip",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    host = "127.0.0.1" if debug else "0.0.0.0"
    app.run(debug=debug, host=host, port=port)
