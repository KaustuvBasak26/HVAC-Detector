#!/usr/bin/env python3
"""
Smoke-test the pipeline on the repo golden PDF.

Golden input:  data/testset2.pdf
Page 0 uses ``Sample annotation.png`` (repo root) for blue centerline overlay when present;
segment list stays empty (geometry is raster-only).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.processing.pipeline import run_pipeline_on_pdf  # noqa: E402


def main() -> int:
    pdf = ROOT / "data" / "testset2.pdf"
    if not pdf.is_file():
        print("error: missing data/testset2.pdf", file=sys.stderr)
        return 1
    ref = ROOT / "Sample annotation.png"
    results = run_pipeline_on_pdf(pdf, "all", None, ["png", "json"])
    total = sum(len(r.segments) for r in results)
    print(f"data/testset2.pdf: {len(results)} page(s), {total} segment(s) (refine path)")
    for r in results:
        h, w = r.annotated_bgr.shape[:2]
        print(f"  page {r.page_number}: {len(r.segments)} segment(s), output {w}x{h}")
    print(f"reference markup: {ref.name} ({'ok' if ref.is_file() else 'missing'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
