from __future__ import annotations

from pathlib import Path

SAMPLE_PDF_ID = "testset2"
SAMPLE_PDF_FILENAME = "testset2.pdf"
SAMPLE_PDF_DESCRIPTION = (
    "Mechanical HVAC floor plan bundled with the project for demo duct detection."
)


def resolved_sample_pdf_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    app_root = Path(__file__).resolve().parents[2]
    candidates = (
        app_root / "samples" / SAMPLE_PDF_FILENAME,
        repo_root / "data" / SAMPLE_PDF_FILENAME,
        repo_root / SAMPLE_PDF_FILENAME,
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[1]
