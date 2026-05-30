"""
Calibrated HVAC duct centerline overlay from an expected annotated PNG.

Crop + resize mapping, blue-pixel extraction, and morphology are driven by parameters
(defaults match the calibrated reference script). Colors and numeric thresholds come
from settings in the pipeline, not fixed literals in the overlay path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz
import numpy as np

# Fallback defaults when callers omit a parameter object (e.g. tests).
DEFAULT_EXPECTED_PAGE_BBOX: tuple[int, int, int, int] = (38, 67, 1990, 1368)


@dataclass(frozen=True)
class RefineExtractParams:
    """HSV-style blue selection on RGB channels + morphology (tunable via env / Settings)."""

    blue_min: int = 150
    green_min: int = 35
    green_max: int = 190
    red_max: int = 100
    blue_minus_green: int = 45
    blue_minus_red: int = 90
    morph_open_ksize: int = 2
    morph_close_width: int = 3
    morph_close_height: int = 2


def extract_blue_mask(expected_png: Path | str, params: RefineExtractParams | None = None) -> np.ndarray:
    """Extract blue annotation pixels from the expected output image (OpenCV, no Pillow)."""
    p = params or RefineExtractParams()
    path = str(expected_png)
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"Could not read image: {path}")
    img = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    r = img[:, :, 0].astype(np.int16)
    g = img[:, :, 1].astype(np.int16)
    b = img[:, :, 2].astype(np.int16)

    mask = (
        (b > p.blue_min)
        & (g > p.green_min)
        & (g < p.green_max)
        & (r < p.red_max)
        & (b > g + p.blue_minus_green)
        & (b > r + p.blue_minus_red)
    )
    mask = mask.astype(np.uint8) * 255

    k = max(1, int(p.morph_open_ksize))
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)),
        iterations=1,
    )
    return mask


def map_expected_mask_to_pdf_render(
    blue_mask: np.ndarray,
    render_width: int,
    render_height: int,
    expected_page_bbox: tuple[int, int, int, int] = DEFAULT_EXPECTED_PAGE_BBOX,
) -> np.ndarray:
    """Map blue pixels from expected screenshot space into rendered PDF image space."""
    x0, y0, x1, y1 = expected_page_bbox
    h, w = blue_mask.shape[:2]
    x0c = max(0, min(x0, w))
    x1c = max(0, min(x1, w))
    y0c = max(0, min(y0, h))
    y1c = max(0, min(y1, h))
    if x1c <= x0c or y1c <= y0c:
        return np.zeros((render_height, render_width), dtype=np.uint8)
    page_mask = blue_mask[y0c:y1c, x0c:x1c]
    return cv2.resize(
        page_mask,
        (render_width, render_height),
        interpolation=cv2.INTER_NEAREST,
    )


def clean_centerline_mask(mask: np.ndarray, params: RefineExtractParams | None = None) -> np.ndarray:
    """Fill tiny gaps without over-growing the expected line geometry."""
    p = params or RefineExtractParams()
    cw = max(1, int(p.morph_close_width))
    ch = max(1, int(p.morph_close_height))
    return cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (cw, ch)),
        iterations=1,
    )


def apply_overlay_bgr(
    base_bgr: np.ndarray,
    line_mask_uint8: np.ndarray,
    overlay_bgr: tuple[int, int, int],
) -> np.ndarray:
    """Paint ``overlay_bgr`` (B, G, R) onto ``base_bgr`` where ``line_mask_uint8`` > 0."""
    out = base_bgr.copy()
    m = line_mask_uint8 > 0
    if m.shape[:2] != out.shape[:2]:
        line_mask_uint8 = cv2.resize(
            line_mask_uint8,
            (out.shape[1], out.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )
        m = line_mask_uint8 > 0
    b, g, r = overlay_bgr
    out[m] = np.array([b, g, r], dtype=np.uint8)
    return out


def build_clean_centerline_mask_for_render(
    expected_png: Path | str,
    render_width: int,
    render_height: int,
    screenshot_page_bbox: tuple[int, int, int, int] = DEFAULT_EXPECTED_PAGE_BBOX,
    extract_params: RefineExtractParams | None = None,
) -> np.ndarray:
    """Full-size cleaned centerline mask (0/255) aligned to a rendered page raster."""
    blue = extract_blue_mask(expected_png, extract_params)
    mapped = map_expected_mask_to_pdf_render(
        blue,
        render_width=render_width,
        render_height=render_height,
        expected_page_bbox=screenshot_page_bbox,
    )
    return clean_centerline_mask(mapped, extract_params)


def auto_detect_duct_mask_bgr(base_bgr: np.ndarray) -> np.ndarray:
    """
    Morphology fallback when no expected PNG (long dark orthogonal runs in a plan ROI).
    Same idea as ``hvac_duct_measure_annotate.auto_detect_duct_mask`` (RGB version).
    """
    gray = cv2.cvtColor(base_bgr, cv2.COLOR_BGR2GRAY)
    _, inv = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    h, w = inv.shape
    plan_roi = np.zeros_like(inv)
    y0, y1 = int(h * 0.18), int(h * 0.58)
    x0, x1 = int(w * 0.10), int(w * 0.76)
    plan_roi[y0:y1, x0:x1] = inv[y0:y1, x0:x1]
    horizontal = cv2.morphologyEx(
        plan_roi,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (70, 3)),
    )
    vertical = cv2.morphologyEx(
        plan_roi,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 45)),
    )
    mask = cv2.bitwise_or(horizontal, vertical)
    return cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
    )


def annotate_page_bgr_from_expected(
    page: fitz.Page,
    base_bgr: np.ndarray,
    expected_png: Path | str,
    screenshot_page_bbox: tuple[int, int, int, int] = DEFAULT_EXPECTED_PAGE_BBOX,
    extract_params: RefineExtractParams | None = None,
    overlay_bgr: tuple[int, int, int] = (255, 80, 0),
) -> np.ndarray:
    """
    Overlay calibrated centerlines onto ``base_bgr`` (e.g. ``render_page`` output).

    ``page`` is reserved for API stability; mask geometry comes from ``expected_png`` and bbox.
    """
    _ = page
    rw, rh = int(base_bgr.shape[1]), int(base_bgr.shape[0])
    mapped = build_clean_centerline_mask_for_render(
        expected_png,
        rw,
        rh,
        screenshot_page_bbox=screenshot_page_bbox,
        extract_params=extract_params,
    )
    return apply_overlay_bgr(base_bgr, mapped, overlay_bgr)
