"""
Extract long, dark *vector* strokes from a PDF page (PyMuPDF get_drawings).

CAD exports keep duct edges as thin stroked lines. Raw get_drawings() also yields grids,
dimensions, and leaders — we keep only near-orthogonal strokes, merge parallel colinear
runs (double-line duct edges), cap stroke width, then emit a small set of quads in raster px.
"""

from __future__ import annotations

import math
import cv2
import fitz
import numpy as np

from app.processing.plan_region_detector import PlanCrop


def _stroke_luminance(color: tuple | None) -> float:
    if not color:
        return 0.0
    r, g, b = color[0], color[1], color[2]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _contour_from_segment_xy(
    x0: float, y0: float, x1: float, y1: float, thick: float
) -> np.ndarray:
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    if L < 1e-3:
        return np.empty((0, 1, 2), dtype=np.int32)
    nx, ny = -dy / L, dx / L
    t = thick * 0.5
    pts = [
        (x0 + nx * t, y0 + ny * t),
        (x1 + nx * t, y1 + ny * t),
        (x1 - nx * t, y1 - ny * t),
        (x0 - nx * t, y0 - ny * t),
    ]
    arr = np.asarray(pts, dtype=np.float32).reshape(-1, 1, 2)
    return np.round(arr).astype(np.int32)


def _segment_mid_inside_crop(
    x0: float, y0: float, x1: float, y1: float, crop: PlanCrop | None
) -> bool:
    if crop is None:
        return True
    mx = (x0 + x1) * 0.5
    my = (y0 + y1) * 0.5
    return crop.x0 <= mx <= crop.x1 and crop.y0 <= my <= crop.y1


def _y_clusters(
    rows: list[tuple[float, float, float, float]], lane_merge_px: float
) -> list[list[tuple[float, float, float, float]]]:
    """rows: (y_mid, a_lo, a_hi, wpt) — cluster by similar y (double-line duct edges)."""
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r[0])
    clusters: list[list[tuple[float, float, float, float]]] = []
    cur: list[tuple[float, float, float, float]] = [rows[0]]
    mean_y = rows[0][0]
    for r in rows[1:]:
        yw = r[0]
        if abs(yw - mean_y) <= lane_merge_px:
            k = len(cur) + 1
            mean_y = mean_y * (k - 1) / k + yw / k
            cur.append(r)
        else:
            clusters.append(cur)
            cur = [r]
            mean_y = yw
    clusters.append(cur)
    return clusters


def _x_clusters(
    cols: list[tuple[float, float, float, float]], lane_merge_px: float
) -> list[list[tuple[float, float, float, float]]]:
    """cols: (x_mid, y_lo, y_hi, wpt) — cluster by similar x (double-line vertical edges)."""
    if not cols:
        return []
    cols = sorted(cols, key=lambda c: c[0])
    clusters: list[list[tuple[float, float, float, float]]] = []
    cur = [cols[0]]
    mean_x = cols[0][0]
    for c in cols[1:]:
        xw = c[0]
        if abs(xw - mean_x) <= lane_merge_px:
            k = len(cur) + 1
            mean_x = mean_x * (k - 1) / k + xw / k
            cur.append(c)
        else:
            clusters.append(cur)
            cur = [c]
            mean_x = xw
    clusters.append(cur)
    return clusters


def _merge_horizontal_intervals(
    cluster: list[tuple[float, float, float, float]],
    lane_gap_max_px: float,
    contain_ratio: float = 0.28,
) -> list[tuple[float, float, float, float]]:
    """
    cluster rows (y_mid, x_lo, x_hi, wpt). Emit (y_mean, x_lo, x_hi, wpt_mean) without
    swallowing short ducts into full-width grid lines when x overlaps.
    """
    segs = sorted(cluster, key=lambda r: (r[1], r[0]))
    out: list[tuple[float, float, float, float]] = []
    cur_lo, cur_hi = segs[0][1], segs[0][2]
    yw_sum, w_sum = segs[0][0] * segs[0][3], segs[0][3]

    def flush_cur() -> None:
        nonlocal cur_lo, cur_hi, yw_sum, w_sum
        if cur_hi > cur_lo:
            wm = max(w_sum, 1e-6)
            out.append((yw_sum / wm, cur_lo, cur_hi, w_sum / wm))

    for y_mid, x_lo, x_hi, wpt in segs[1:]:
        span_c = cur_hi - cur_lo
        span_n = x_hi - x_lo
        touch = x_lo <= cur_hi + lane_gap_max_px and x_hi >= cur_lo - lane_gap_max_px
        small_inside = (
            span_n < contain_ratio * max(span_c, 48.0)
            and x_lo >= cur_lo - 1.5
            and x_hi <= cur_hi + 1.5
        )
        if small_inside and span_c > span_n + 6.0:
            out.append((y_mid, x_lo, x_hi, wpt))
            continue
        if touch:
            cur_lo = min(cur_lo, x_lo)
            cur_hi = max(cur_hi, x_hi)
            yw_sum += y_mid * wpt
            w_sum += wpt
        else:
            flush_cur()
            cur_lo, cur_hi = x_lo, x_hi
            yw_sum, w_sum = y_mid * wpt, wpt
    flush_cur()
    return out


def _merge_vertical_intervals(
    cluster: list[tuple[float, float, float, float]],
    lane_gap_max_px: float,
    contain_ratio: float = 0.28,
) -> list[tuple[float, float, float, float]]:
    """cluster cols (x_mid, y_lo, y_hi, wpt) → (x_mean, y_lo, y_hi, wpt_mean)."""
    segs = sorted(cluster, key=lambda r: (r[1], r[0]))
    out: list[tuple[float, float, float, float]] = []
    cur_lo, cur_hi = segs[0][1], segs[0][2]
    xw_sum, w_sum = segs[0][0] * segs[0][3], segs[0][3]

    def flush_cur() -> None:
        nonlocal cur_lo, cur_hi, xw_sum, w_sum
        if cur_hi > cur_lo:
            wm = max(w_sum, 1e-6)
            out.append((xw_sum / wm, cur_lo, cur_hi, w_sum / wm))

    for x_mid, y_lo, y_hi, wpt in segs[1:]:
        span_c = cur_hi - cur_lo
        span_n = y_hi - y_lo
        touch = y_lo <= cur_hi + lane_gap_max_px and y_hi >= cur_lo - lane_gap_max_px
        small_inside = (
            span_n < contain_ratio * max(span_c, 48.0)
            and y_lo >= cur_lo - 1.5
            and y_hi <= cur_hi + 1.5
        )
        if small_inside and span_c > span_n + 6.0:
            out.append((x_mid, y_lo, y_hi, wpt))
            continue
        if touch:
            cur_lo = min(cur_lo, y_lo)
            cur_hi = max(cur_hi, y_hi)
            xw_sum += x_mid * wpt
            w_sum += wpt
        else:
            flush_cur()
            cur_lo, cur_hi = y_lo, y_hi
            xw_sum, w_sum = x_mid * wpt, wpt
    flush_cur()
    return out


def collect_vector_line_contours(
    page: fitz.Page,
    zoom: float,
    img_w: int,
    img_h: int,
    min_len_px: float = 200.0,
    min_stroke_pt: float = 0.06,
    max_stroke_pt: float = 2.4,
    max_skew: float = 0.2,
    lane_merge_px: float = 10.0,
    lane_gap_max_px: float = 34.0,
    min_raw_len_px: float = 52.0,
    max_drawings_scan: int = 120_000,
    max_output: int = 160,
    plan_crop: PlanCrop | None = None,
) -> list[tuple[np.ndarray, tuple[int, int, int, int]]]:
    """
    Returns (contour Nx1x2 int32 in **raster page pixels**, bbox xyxy) for merged strokes.
    """
    zw = float(zoom)
    raw_h: list[tuple[float, float, float, float]] = []
    raw_v: list[tuple[float, float, float, float]] = []
    scanned = 0

    for path in page.get_drawings():
        scanned += 1
        if scanned > max_drawings_scan:
            break
        ptype = path.get("type") or ""
        if ptype == "f":
            continue
        wpt = path.get("width")
        if wpt is None:
            wpt = 0.25
        if wpt < min_stroke_pt or wpt > max_stroke_pt:
            continue
        col = path.get("color")
        if col is not None and _stroke_luminance(col) > 0.72:
            continue

        for it in path.get("items", ()):
            if it[0] != "l":
                continue
            p1, p2 = it[1], it[2]
            x0, y0 = p1.x * zw, p1.y * zw
            x1, y1 = p2.x * zw, p2.y * zw
            dx, dy = abs(x1 - x0), abs(y1 - y0)
            Lpx = math.hypot(dx, dy)
            if Lpx < min_raw_len_px:
                continue
            if max(x0, x1) < -2 or min(x0, x1) > img_w + 2:
                continue
            if max(y0, y1) < -2 or min(y0, y1) > img_h + 2:
                continue
            if not _segment_mid_inside_crop(x0, y0, x1, y1, plan_crop):
                continue
            # Near-horizontal: |dy| / |dx| <= max_skew
            if dx > 1e-6 and dy <= max_skew * dx:
                y_mid = (y0 + y1) * 0.5
                raw_h.append((y_mid, min(x0, x1), max(x0, x1), float(wpt)))
            elif dy > 1e-6 and dx <= max_skew * dy:
                x_mid = (x0 + x1) * 0.5
                raw_v.append((x_mid, min(y0, y1), max(y0, y1), float(wpt)))

    merged_h: list[tuple[float, float, float, float]] = []
    for cl in _y_clusters(raw_h, lane_merge_px):
        merged_h.extend(_merge_horizontal_intervals(cl, lane_gap_max_px))
    merged_v: list[tuple[float, float, float, float]] = []
    for cl in _x_clusters(raw_v, lane_merge_px):
        merged_v.extend(_merge_vertical_intervals(cl, lane_gap_max_px))

    out: list[tuple[np.ndarray, tuple[int, int, int, int], float]] = []

    for y_mean, x_lo, x_hi, wpt in merged_h:
        span = x_hi - x_lo
        if span < min_len_px:
            continue
        th = max(2.0, min(9.0, float(wpt) * zw * 0.82))
        cnt = _contour_from_segment_xy(x_lo, y_mean, x_hi, y_mean, th)
        if cnt.size < 8:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        fb = (x, y, x + bw, y + bh)
        out.append((cnt, fb, span))

    for x_mean, y_lo, y_hi, wpt in merged_v:
        span = y_hi - y_lo
        if span < min_len_px:
            continue
        th = max(2.0, min(9.0, float(wpt) * zw * 0.82))
        cnt = _contour_from_segment_xy(x_mean, y_lo, x_mean, y_hi, th)
        if cnt.size < 8:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        fb = (x, y, x + bw, y + bh)
        out.append((cnt, fb, span))

    out.sort(key=lambda t: t[2], reverse=True)
    trimmed = [(t[0], t[1]) for t in out[:max_output]]
    return trimmed
