"""
Distance-to-ink maps for rectangular HVAC ducts drawn as double lines.

Sheet grids are single-width strokes: a polyline on that stroke sits on ink, so the mean
distance to the nearest ink pixel is tiny. Real duct centerlines sit in the bright gap
between parallel walls, so the mean distance is noticeably larger.
"""

from __future__ import annotations

import math

import cv2
import numpy as np


def build_ink_mask_union(gray_u8: np.ndarray) -> np.ndarray:
    """Binary 255 on dark CAD ink (union of two adaptive passes, stable on MEP backgrounds)."""
    blur = cv2.GaussianBlur(gray_u8, (3, 3), 0)
    th1 = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 6
    )
    th2 = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 5
    )
    return cv2.bitwise_or(th1, th2)


def build_corridor_dt_map(gray_u8: np.ndarray) -> np.ndarray:
    """
    For each pixel, L2 distance in pixels to the nearest dark-ink pixel (``build_ink_mask_union``).
    Values are large in the middle of double-line duct gaps and small on / beside hairlines.
    """
    ink = build_ink_mask_union(gray_u8)
    # Distance to nearest zero pixel; ink = 0 so paper pixels get distance-to-ink.
    src = np.where(ink > 128, 0, 1).astype(np.uint8)
    return cv2.distanceTransform(src, cv2.DIST_L2, 5).astype(np.float32)


def polyline_median_corridor_dt(
    dt_crop: np.ndarray,
    poly_page: list[tuple[float, float]],
    crop_x0: int,
    crop_y0: int,
    *,
    step_px: float = 4.0,
) -> float:
    """Median corridor DT along ``poly_page`` (full-page px) sampled into ``dt_crop`` coords."""
    if len(poly_page) < 2 or dt_crop.size == 0:
        return 0.0
    h, w = dt_crop.shape[:2]
    vals: list[float] = []
    for i in range(len(poly_page) - 1):
        ax, ay = float(poly_page[i][0]), float(poly_page[i][1])
        bx, by = float(poly_page[i + 1][0]), float(poly_page[i + 1][1])
        seg_len = math.hypot(bx - ax, by - ay)
        if seg_len < 1e-3:
            continue
        n_steps = max(1, int(seg_len / max(step_px, 0.5)))
        for s in range(n_steps + 1):
            t = s / n_steps
            xi = int(round(ax + t * (bx - ax))) - int(crop_x0)
            yi = int(round(ay + t * (by - ay))) - int(crop_y0)
            if 0 <= xi < w and 0 <= yi < h:
                vals.append(float(dt_crop[yi, xi]))
    if not vals:
        return 0.0
    return float(np.median(np.asarray(vals, dtype=np.float32)))


def polyline_robust_corridor_dt(
    dt_crop: np.ndarray,
    poly_page: list[tuple[float, float]],
    crop_x0: int,
    crop_y0: int,
    *,
    step_px: float = 4.0,
    perp_half: int = 4,
) -> float:
    """
    Like ``polyline_median_corridor_dt`` but each sample uses the **max** DT along a few pixels
    on the segment normal. Skeletonized centerlines often graze one wall; the gap center is
    offset by a pixel or two — max pooling recovers the corridor depth MEP markups follow.
    """
    if len(poly_page) < 2 or dt_crop.size == 0:
        return 0.0
    h, w = dt_crop.shape[:2]
    ph = max(0, int(perp_half))
    sample_maxes: list[float] = []
    for i in range(len(poly_page) - 1):
        ax, ay = float(poly_page[i][0]), float(poly_page[i][1])
        bx, by = float(poly_page[i + 1][0]), float(poly_page[i + 1][1])
        seg_len = math.hypot(bx - ax, by - ay)
        if seg_len < 1e-3:
            continue
        nx = -(by - ay) / seg_len
        ny = (bx - ax) / seg_len
        n_steps = max(1, int(seg_len / max(step_px, 0.5)))
        for s in range(n_steps + 1):
            t = s / n_steps
            xi = ax + t * (bx - ax)
            yi = ay + t * (by - ay)
            local_best = -1.0
            for k in range(-ph, ph + 1):
                px = int(round(xi + k * nx)) - int(crop_x0)
                py = int(round(yi + k * ny)) - int(crop_y0)
                if 0 <= px < w and 0 <= py < h:
                    v = float(dt_crop[py, px])
                    if v > local_best:
                        local_best = v
            if local_best >= 0:
                sample_maxes.append(local_best)
    if not sample_maxes:
        return 0.0
    return float(np.median(np.asarray(sample_maxes, dtype=np.float32)))


def corridor_ridge_mask(
    gray_u8: np.ndarray,
    *,
    min_dt: float,
    max_dt: float,
    close_ksize: int = 3,
) -> np.ndarray:
    """
    Pixels whose distance-to-ink lies in [min_dt, max_dt] — medial sheet of double-line runs.
    Morph close reconnects small breaks inside the same duct.
    """
    dt = build_corridor_dt_map(gray_u8)
    ridge = ((dt >= min_dt) & (dt <= max_dt)).astype(np.uint8) * 255
    k = max(3, int(close_ksize) | 1)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    ridge = cv2.morphologyEx(ridge, cv2.MORPH_CLOSE, ker, iterations=2)
    return ridge
