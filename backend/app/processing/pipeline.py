from __future__ import annotations

import gc
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz
import numpy as np

from app.core.config import settings, effective_page_render_dpi
from app.processing.dimension_parser import ParsedDimension
from app.processing.duct_measure_annotate import (
    draw_measure_overlay_bgr,
    extract_line_annotations_pixel,
    segments_from_centerline_mask,
)
from app.processing.exporter import export_segments_csv, export_segments_json
from app.processing.measurement_engine import measure_segment_length_ft
from app.processing.pdf_loader import validate_and_open
from app.processing.plan_region_detector import centroid_in_markup_zones
from app.processing.refine_hvac_centerlines import (
    RefineExtractParams,
    apply_overlay_bgr,
    auto_detect_duct_mask_bgr,
    build_clean_centerline_mask_for_render,
    clean_centerline_mask,
)
from app.processing.renderer import render_page
from app.processing.scale_detector import ScaleInfo, detect_scale
from app.processing.segment_builder import SegmentModel
from app.processing.text_extractor import TextBlock, extract_words_scaled


@dataclass
class PagePipelineResult:
    page_number: int
    annotated_bgr: np.ndarray
    segments: list[SegmentModel]
    labels: dict[str, tuple[ParsedDimension | None, float]]
    lengths: dict[str, tuple[float | None, str]]
    scale: ScaleInfo


def _filter_text_blocks_to_plan(blocks: list[TextBlock], img_w: int, img_h: int) -> list[TextBlock]:
    kept: list[TextBlock] = []
    for b in blocks:
        x0, y0, x1, y1 = b.bbox
        ibox = (int(x0), int(y0), int(x1), int(y1))
        if centroid_in_markup_zones(ibox, img_w, img_h):
            continue
        kept.append(b)
    return kept


def _refine_extract_params() -> RefineExtractParams:
    return RefineExtractParams(
        blue_min=int(settings.refine_blue_min_b),
        green_min=int(settings.refine_blue_min_g),
        green_max=int(settings.refine_blue_max_g),
        red_max=int(settings.refine_blue_max_r),
        blue_minus_green=int(settings.refine_blue_minus_green),
        blue_minus_red=int(settings.refine_blue_minus_red),
        morph_open_ksize=int(settings.refine_morph_open_ksize),
        morph_close_width=int(settings.refine_morph_close_w),
        morph_close_height=int(settings.refine_morph_close_h),
    )


def _parse_screenshot_bbox(s: str) -> tuple[int, int, int, int]:
    parts = [int(x.strip()) for x in s.split(",")]
    if len(parts) != 4:
        raise ValueError(
            "HVAC_REFINE_SCREENSHOT_PAGE_BBOX must be four comma-separated integers: x0,y0,x1,y1"
        )
    return (parts[0], parts[1], parts[2], parts[3])


def _page_indices(doc: fitz.Document, mode: str, numbers: list[int]) -> list[int]:
    """
    Empty ``numbers`` → every page. If ``numbers`` is set, use those 1-based page indices
    (so API jobs can target a subset even when the client reuses mode ``all`` by mistake).
    """
    if numbers:
        out = [int(n) - 1 for n in numbers if 1 <= int(n) <= doc.page_count]
        return sorted(set(out)) if out else list(range(doc.page_count))
    return list(range(doc.page_count))


def run_pipeline_on_pdf(
    pdf_path: Path,
    page_selection_mode: str = "all",
    page_numbers: list[int] | None = None,
    output_formats: list[str] | None = None,
    on_progress: Callable[[int, str], None] | None = None,
) -> list[PagePipelineResult]:
    output_formats = output_formats or ["png", "pdf", "json"]
    doc = validate_and_open(pdf_path)
    try:
        indices = _page_indices(doc, page_selection_mode, page_numbers or [])
        if not indices:
            indices = [0]
        if settings.low_memory_mode and len(indices) > settings.low_memory_max_pages:
            indices = indices[: settings.low_memory_max_pages]
        results: list[PagePipelineResult] = []
        total_pages = len(indices)
        expected_path = Path(settings.expected_annotation_png)
        bbox = _parse_screenshot_bbox(settings.refine_screenshot_page_bbox)
        refine_target = int(settings.refine_expected_png_target_page)
        refine_extract = _refine_extract_params()
        overlay_bgr = (
            int(settings.refine_overlay_bgr_b),
            int(settings.refine_overlay_bgr_g),
            int(settings.refine_overlay_bgr_r),
        )
        for pos, idx in enumerate(indices):
            if on_progress is not None:
                pct = 8 + int(72 * pos / max(total_pages, 1))
                on_progress(
                    pct,
                    f"Page {pos + 1} of {total_pages}: rendering and centerline overlay",
                )
            page = doc[idx]
            page_dpi = effective_page_render_dpi(float(page.rect.width), float(page.rect.height))
            pr = render_page(doc, idx, page_dpi)
            # NumPy/OpenCV images are (height, width, ...); keep names consistent everywhere.
            ih, iw = pr.image_bgr.shape[:2]
            page = doc[idx]
            line_ann = extract_line_annotations_pixel(page, pr.scale_x, pr.scale_y)

            use_cal_mask = (
                not settings.low_memory_mode
                and expected_path.is_file()
                and refine_target > 0
                and (idx + 1) == refine_target
            )
            if use_cal_mask:
                mask = build_clean_centerline_mask_for_render(
                    expected_path,
                    iw,
                    ih,
                    screenshot_page_bbox=bbox,
                    extract_params=refine_extract,
                )
            else:
                mask = auto_detect_duct_mask_bgr(pr.image_bgr)
                mask = clean_centerline_mask(mask, refine_extract)

            scale_fpi = float(settings.default_feet_per_drawing_inch or 4.0)
            segments, labels, lengths, pdf_notes = segments_from_centerline_mask(
                mask,
                page,
                line_ann,
                idx + 1,
                scale_fpi,
            )

            words = extract_words_scaled(doc, idx, pr.scale_x, pr.scale_y)
            words = _filter_text_blocks_to_plan(words, iw, ih)
            scale = detect_scale(words, float(pr.dpi))
            default_fpp: float | None = None
            if scale.feet_per_pixel is None and settings.default_feet_per_drawing_inch:
                default_fpp = settings.default_feet_per_drawing_inch / float(pr.dpi)

            for seg in segments:
                lengths[seg.segment_id] = measure_segment_length_ft(
                    seg, scale, default_fpp
                )

            annotated = apply_overlay_bgr(pr.image_bgr, mask, overlay_bgr)
            if settings.refine_draw_measure_labels and not settings.low_memory_mode:
                annotated = draw_measure_overlay_bgr(
                    annotated,
                    segments,
                    line_ann,
                    lengths,
                    labels,
                    pdf_notes,
                )

            results.append(
                PagePipelineResult(
                    page_number=idx + 1,
                    annotated_bgr=annotated,
                    segments=segments,
                    labels=labels,
                    lengths=lengths,
                    scale=scale,
                )
            )
            if on_progress is not None:
                pct_done = 8 + int(72 * (pos + 1) / max(total_pages, 1))
                on_progress(
                    min(82, pct_done),
                    f"Page {pos + 1} of {total_pages}: annotations ready",
                )
            if settings.low_memory_mode:
                del mask, pr, line_ann, words
                gc.collect()
        return results
    finally:
        doc.close()


def write_pipeline_outputs(
    results: list[PagePipelineResult],
    job_dir: Path,
    job_id: str,
    output_formats: list[str],
) -> dict[str, str]:
    job_dir.mkdir(parents=True, exist_ok=True)
    out_dir = job_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    keys: dict[str, str] = {}
    prefix = f"jobs/{job_id}/outputs"

    all_segments: list[SegmentModel] = []
    all_labels: dict[str, tuple[ParsedDimension | None, float]] = {}
    all_lengths: dict[str, tuple[float | None, str]] = {}

    for r in results:
        all_segments.extend(r.segments)
        all_labels.update(r.labels)
        all_lengths.update(r.lengths)

    if "png" in output_formats and results:
        png_path = out_dir / "annotated.png"
        cv2.imwrite(str(png_path), results[0].annotated_bgr)
        keys["annotated_png"] = f"{prefix}/annotated.png"

    if "json" in output_formats:
        json_path = out_dir / "segments.json"
        export_segments_json(json_path, all_segments, all_labels, all_lengths)
        keys["segments_json"] = f"{prefix}/segments.json"

    if "csv" in output_formats:
        csv_path = out_dir / "segments.csv"
        export_segments_csv(csv_path, all_segments, all_labels, all_lengths)
        keys["segments_csv"] = f"{prefix}/segments.csv"

    if "pdf" in output_formats and results:
        pdf_path = out_dir / "annotated.pdf"
        _write_annotated_pdf(results, pdf_path)
        keys["annotated_pdf"] = f"{prefix}/annotated.pdf"

    return keys


def _write_annotated_pdf(results: list[PagePipelineResult], path: Path) -> None:
    doc = fitz.open()
    try:
        for r in results:
            h, w = r.annotated_bgr.shape[:2]
            page = doc.new_page(width=w, height=h)
            ok, buf = cv2.imencode(".png", r.annotated_bgr)
            if not ok:
                raise RuntimeError("png_encode_failed")
            page.insert_image(page.rect, stream=buf.tobytes())
        doc.save(path)
    finally:
        doc.close()
