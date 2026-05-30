from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class PlanCrop:
    x0: int
    y0: int
    x1: int
    y1: int


def detect_plan_region(
    gray: np.ndarray,
    title_right_frac: float = 0.26,
    notes_bottom_frac: float = 0.34,
    margin_frac: float = 0.015,
) -> PlanCrop:
    """
    Crop to the live floor-plan area. M-series sheets usually place the title block on the
    right and GENERAL / PLAN NOTES in a wide band at the bottom — those must stay *out* of
    the detection ROI or morphology will latch onto note text as false “ducts”.
    """
    h, w = gray.shape[:2]
    mx = int(w * margin_frac)
    my = int(h * margin_frac)
    # Drop a thin band under the sheet border / column grid (reduces false duct hits)
    x0, y0 = mx, my + int(h * 0.042)
    x1 = int(w * (1.0 - title_right_frac)) - mx
    y1 = int(h * (1.0 - notes_bottom_frac)) - my
    x1 = max(x0 + 50, x1)
    y1 = max(y0 + 50, y1)
    y0 = min(y0, max(my, y1 - 80))
    return PlanCrop(x0=x0, y0=y0, x1=x1, y1=y1)


def edge_density_refine(gray: np.ndarray, base: PlanCrop) -> PlanCrop:
    """Optionally trim a *small* strip at the bottom when edge density spikes (notes)."""
    roi = gray[base.y0 : base.y1, base.x0 : base.x1]
    if roi.size == 0:
        return base
    edges = cv2.Canny(cv2.GaussianBlur(roi, (5, 5), 0), 40, 120)
    row_sum = edges.sum(axis=1).astype(np.float64)
    if row_sum.size < 20:
        return base
    h = row_sum.shape[0]
    mid = h // 2
    top_m = row_sum[:mid].mean() + 1e-6
    tail = row_sum[int(h * 0.75) :].mean()
    if tail > top_m * 2.5:
        # At most remove ~12% of ROI height so real plan geometry near the kitchen is kept
        trim_rows = min(int(h * 0.12), int(h * 0.25))
        new_y1 = base.y0 + h - trim_rows
        return PlanCrop(x0=base.x0, y0=base.y0, x1=base.x1, y1=min(base.y1, new_y1))
    return base


def centroid_in_markup_zones(
    bbox: tuple[int, int, int, int],
    img_w: int,
    img_h: int,
    bottom_frac: float = 0.36,
    right_frac: float = 0.28,
    top_frac: float = 0.026,
    left_frac: float = 0.012,
) -> bool:
    """
    True if bbox center lies in sheet bands where we almost never have real duct geometry:
    title / grid (top & left), notes (bottom), title block (right).
    """
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    if cy <= img_h * top_frac:
        return True
    if cx <= img_w * left_frac:
        return True
    if cy >= img_h * (1.0 - bottom_frac):
        return True
    if cx >= img_w * (1.0 - right_frac):
        return True
    return False


def bbox_center_inside_plan_crop(
    bbox_xyxy: tuple[int, int, int, int],
    crop: PlanCrop,
    inset_frac: float = 0.0,
) -> bool:
    """True if bbox center lies strictly inside the plan crop (kills title margins / notes)."""
    x0, y0, x1, y1 = bbox_xyxy
    cx = (x0 + x1) * 0.5
    cy = (y0 + y1) * 0.5
    cw = max(1, crop.x1 - crop.x0)
    ch = max(1, crop.y1 - crop.y0)
    ix = cw * inset_frac * 0.5
    iy = ch * inset_frac * 0.5
    return (
        crop.x0 + ix <= cx <= crop.x1 - ix
        and crop.y0 + iy <= cy <= crop.y1 - iy
    )


def polyline_fraction_inside_crop(
    poly: list[tuple[float, float]],
    crop: PlanCrop,
) -> float:
    """Fraction of polyline edge length whose midpoints lie inside the plan crop (page px)."""
    if not poly:
        return 0.0
    if len(poly) < 2:
        mx, my = float(poly[0][0]), float(poly[0][1])
        return (
            1.0
            if crop.x0 <= mx <= crop.x1 and crop.y0 <= my <= crop.y1
            else 0.0
        )
    inside = 0.0
    total = 0.0
    for i in range(len(poly) - 1):
        ax, ay = float(poly[i][0]), float(poly[i][1])
        bx, by = float(poly[i + 1][0]), float(poly[i + 1][1])
        d = math.hypot(bx - ax, by - ay)
        if d < 1e-6:
            continue
        total += d
        mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
        if crop.x0 <= mx <= crop.x1 and crop.y0 <= my <= crop.y1:
            inside += d
    return inside / max(total, 1e-6)


def segment_bbox_escapes_plan_extent(
    bbox_xyxy: tuple[int, int, int, int],
    crop: PlanCrop,
    tolerance: int = 24,
) -> bool:
    """
    True for long construction lines that pierce *past* the plan crop (e.g. full-height
    grid / border strokes continuing into GENERAL NOTES).
    """
    x0, y0, x1, y1 = bbox_xyxy
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    if y1 > crop.y1 + tolerance or y0 < crop.y0 - tolerance:
        if bw * 4 <= bh:
            return True
    if x1 > crop.x1 + tolerance or x0 < crop.x0 - tolerance:
        if bh * 4 <= bw:
            return True
    return False


def bbox_resembles_plan_axis_grid(
    bbox_xyxy: tuple[int, int, int, int],
    crop: PlanCrop,
    span_frac: float = 0.88,
) -> bool:
    """
    Near full-width / full-height *hairline* inside the crop (structural grid), not a duct
    run — ducts have a larger cross-section in the bbox than a 1–2 pt CAD grid stroke.
    Caps avoid classifying double-line mains (taller merged masks) as sheet grids.
    """
    x0, y0, x1, y1 = bbox_xyxy
    cw = max(1, crop.x1 - crop.x0)
    ch = max(1, crop.y1 - crop.y0)
    cx0, cy0 = max(x0, crop.x0), max(y0, crop.y0)
    cx1, cy1 = min(x1, crop.x1), min(y1, crop.y1)
    if cx1 <= cx0 or cy1 <= cy0:
        return False
    ibw, ibh = cx1 - cx0, cy1 - cy0
    max_thick_h = min(26, max(12, int(ch * 0.023)))
    max_thick_w = min(26, max(12, int(cw * 0.023)))
    if ibw >= cw * span_frac and ibh <= max_thick_h:
        return True
    if ibh >= ch * span_frac and ibw <= max_thick_w:
        return True
    return False


def bbox_page_axis_bleed(
    bbox_xyxy: tuple[int, int, int, int],
    img_w: int,
    img_h: int,
    span_frac: float = 0.84,
) -> bool:
    """Spans almost the entire sheet horizontally or vertically (sheet frame / bleed grid)."""
    x0, y0, x1, y1 = bbox_xyxy
    bw, bh = x1 - x0, y1 - y0
    if bw >= img_w * span_frac and bh <= max(18, int(img_h * 0.055)):
        return True
    if bh >= img_h * span_frac and bw <= max(18, int(img_w * 0.055)):
        return True
    return False


def bbox_center_in_plan_upper_void(
    bbox_xyxy: tuple[int, int, int, int],
    crop: PlanCrop,
    frac: float = 0.095,
) -> bool:
    """
    True if the segment sits in the top band of the *plan crop* (common blank margin /
    column grid above the floor line). Full-page top_frac alone misses this because the
    crop still includes white space above the drawing.
    """
    ph = crop.y1 - crop.y0
    if ph < 100:
        return False
    cy = (bbox_xyxy[1] + bbox_xyxy[3]) * 0.5
    y_rel = cy - crop.y0
    return y_rel < ph * frac


def polyline_resembles_horizontal_sheet_grid(
    poly: list[tuple[float, float]],
    crop: PlanCrop,
    *,
    min_x_span_frac: float = 0.72,
    max_y_span_px: int = 38,
    max_y_span_frac: float = 0.058,
    band_top_frac: float = 0.12,
    band_bottom_frac: float = 0.12,
) -> bool:
    """
    Long, nearly horizontal polylines that are very thin in Y and sit in the top or bottom
    band of the plan crop — typical architectural column / dimension grids (not duct mains).
    """
    if len(poly) < 2:
        return False
    cw = max(1, crop.x1 - crop.x0)
    ch = max(1, crop.y1 - crop.y0)
    if cw < 120 or ch < 120:
        return False
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    x0p, x1p = min(xs), max(xs)
    y0p, y1p = min(ys), max(ys)
    x_span = x1p - x0p
    y_span = y1p - y0p
    if x_span < cw * min_x_span_frac:
        return False
    y_cap = max(float(max_y_span_px), ch * max_y_span_frac)
    if y_span > y_cap:
        return False
    if x_span < y_span * 6.0:
        return False
    my = 0.5 * (y0p + y1p)
    y_rel = my - crop.y0
    rel = y_rel / ch
    return rel < band_top_frac or rel > (1.0 - band_bottom_frac)


def polyline_resembles_vertical_sheet_grid(
    poly: list[tuple[float, float]],
    crop: PlanCrop,
    *,
    min_y_span_frac: float = 0.68,
    max_x_span_px: int = 40,
    max_x_span_frac: float = 0.06,
    band_left_frac: float = 0.09,
    band_right_frac: float = 0.08,
) -> bool:
    """Tall thin vertical strokes hugging the left/right plan margin (column grid)."""
    if len(poly) < 2:
        return False
    cw = max(1, crop.x1 - crop.x0)
    ch = max(1, crop.y1 - crop.y0)
    if cw < 120 or ch < 120:
        return False
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    x0p, x1p = min(xs), max(xs)
    y0p, y1p = min(ys), max(ys)
    x_span = x1p - x0p
    y_span = y1p - y0p
    if y_span < ch * min_y_span_frac:
        return False
    x_cap = max(float(max_x_span_px), cw * max_x_span_frac)
    if x_span > x_cap:
        return False
    if y_span < x_span * 5.5:
        return False
    mx = 0.5 * (x0p + x1p)
    x_rel = mx - crop.x0
    rel = x_rel / cw
    return rel < band_left_frac or rel > (1.0 - band_right_frac)
