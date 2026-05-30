"""
Reject segments that do not sit on dark printed linework — cuts grid ticks, pale margins,
and many non-duct blobs while keeping real HVAC runs (black / dark gray on the sheet).
"""

from __future__ import annotations

import math

import numpy as np


def polyline_dark_cover_fraction(
    gray_u8: np.ndarray,
    poly: list[tuple[float, float]],
    *,
    step_px: float = 5.0,
    gray_thresh: int = 198,
    neighborhood: int = 1,
    perpendicular_half_span: int = 0,
) -> float:
    """
    Fraction of samples along ``poly`` where local min intensity is below ``gray_thresh``.

    Double-line ducts often leave the geometric centerline in the bright gap between walls.
    When ``perpendicular_half_span`` > 0, each sample also considers pixels stepped along the
    segment normal (±1…±span), and uses the minimum over the small square patch plus those
    probes — so a centerline in the gap still “sees” the parallel ink without widening the
    square so much that unrelated dark pixels dominate.
    """
    if len(poly) < 2 or gray_u8.size == 0:
        return 0.0
    h, w = gray_u8.shape[:2]
    nh = max(0, int(neighborhood))
    ph = max(0, int(perpendicular_half_span))
    hits = 0
    total = 0
    for i in range(len(poly) - 1):
        ax, ay = float(poly[i][0]), float(poly[i][1])
        bx, by = float(poly[i + 1][0]), float(poly[i + 1][1])
        seg_len = math.hypot(bx - ax, by - ay)
        if seg_len < 1e-3:
            continue
        nx = -(by - ay) / seg_len
        ny = (bx - ax) / seg_len
        n_steps = max(1, int(seg_len / max(step_px, 0.5)))
        for s in range(n_steps + 1):
            t = s / n_steps
            xi = int(round(ax + t * (bx - ax)))
            yi = int(round(ay + t * (by - ay)))
            if xi < 0 or yi < 0 or xi >= w or yi >= h:
                continue
            y0, y1 = max(0, yi - nh), min(h, yi + nh + 1)
            x0, x1 = max(0, xi - nh), min(w, xi + nh + 1)
            patch = gray_u8[y0:y1, x0:x1]
            if patch.size == 0:
                continue
            local_min = int(patch.min())
            if ph > 0:
                for k in range(1, ph + 1):
                    for sgn in (-1, 1):
                        x2 = int(round(xi + sgn * k * nx))
                        y2 = int(round(yi + sgn * k * ny))
                        if 0 <= x2 < w and 0 <= y2 < h:
                            v = int(gray_u8[y2, x2])
                            if v < local_min:
                                local_min = v
            total += 1
            if local_min < gray_thresh:
                hits += 1
    return hits / max(total, 1)


def polyline_axis_hairline_center_fraction(
    gray_u8: np.ndarray,
    poly: list[tuple[float, float]],
    *,
    step_px: float = 5.0,
    perp_half: int = 10,
) -> float:
    """
    Fraction of samples where the **darkest** pixel along the segment normal lies at (or
    immediately beside) the center sample. Single-width column / row grid strokes peak at the
    stroke center; double-line HVAC ducts usually leave the traced centerline in a brighter
    gap with darker ink offset to each side, so the intensity minimum shifts away from center.
    """
    if len(poly) < 2 or gray_u8.size == 0:
        return 0.0
    h, w = gray_u8.shape[:2]
    P = max(2, int(perp_half))
    hits = 0
    total = 0
    for i in range(len(poly) - 1):
        ax, ay = float(poly[i][0]), float(poly[i][1])
        bx, by = float(poly[i + 1][0]), float(poly[i + 1][1])
        seg_len = math.hypot(bx - ax, by - ay)
        if seg_len < 1e-3:
            continue
        nx = -(by - ay) / seg_len
        ny = (bx - ax) / seg_len
        n_steps = max(1, int(seg_len / max(step_px, 0.5)))
        for s in range(n_steps + 1):
            t = s / n_steps
            xi = int(round(ax + t * (bx - ax)))
            yi = int(round(ay + t * (by - ay)))
            if xi < 0 or yi < 0 or xi >= w or yi >= h:
                continue
            vals: list[int] = []
            for k in range(-P, P + 1):
                x2 = int(round(xi + k * nx))
                y2 = int(round(yi + k * ny))
                if 0 <= x2 < w and 0 <= y2 < h:
                    vals.append(int(gray_u8[y2, x2]))
                else:
                    vals.append(255)
            imn = int(np.argmin(np.asarray(vals, dtype=np.int32)))
            center = P
            total += 1
            if abs(imn - center) <= 1:
                hits += 1
    return hits / max(total, 1)
