import json
import math
from dataclasses import dataclass

import cv2
import numpy as np

from app.processing.duct_detector import DuctCandidate
from app.processing.skeleton_path import skeleton_polyline_from_contour


@dataclass
class SegmentModel:
    segment_id: str
    page_number: int
    polyline: list[tuple[float, float]]
    bbox: tuple[int, int, int, int]
    shape: str
    segment_type: str
    confidence: float
    # For on-plan ID tags: CC centroid + axis (matches hvac_duct_measure_legend_enhanced.DuctSegment).
    centroid_x: float | None = None
    centroid_y: float | None = None
    label_orientation: str = "angled"


def contour_centerline_and_bbox(cnt: np.ndarray) -> tuple[list[tuple[float, float]], tuple[int, int, int, int]]:
    x, y, bw, bh = cv2.boundingRect(cnt)
    bbox = (x, y, x + bw, y + bh)
    xc = x + bw / 2
    yc = y + bh / 2
    if bw >= bh:
        poly = [(float(x), float(yc)), (float(x + bw), float(yc))]
    else:
        poly = [(float(xc), float(y)), (float(xc), float(y + bh))]
    return poly, bbox


def contour_oriented_centerline(
    cnt: np.ndarray,
) -> tuple[list[tuple[float, float]], tuple[int, int, int, int]]:
    """
    Principal-axis segment through the contour (handles diagonal runs). Falls back to
    axis-aligned bbox centerline for tiny or degenerate shapes.
    """
    x, y, bw, bh = cv2.boundingRect(cnt)
    bbox = (x, y, x + bw, y + bh)
    pts = np.asarray(cnt, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] < 5 or bw < 3 or bh < 3:
        return contour_centerline_and_bbox(cnt)
    mean = pts.mean(axis=0)
    centered = pts - mean
    try:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return contour_centerline_and_bbox(cnt)
    direction = vt[0]
    n = float(np.hypot(direction[0], direction[1]))
    if n < 1e-6:
        return contour_centerline_and_bbox(cnt)
    direction = direction / n
    proj = centered @ direction
    t0, t1 = float(proj.min()), float(proj.max())
    if t1 - t0 < 1.0:
        return contour_centerline_and_bbox(cnt)
    p0 = mean + direction * t0
    p1 = mean + direction * t1
    return [(float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1]))], bbox


def _polyline_length(poly: list[tuple[float, float]]) -> float:
    s = 0.0
    for i in range(len(poly) - 1):
        a, b = poly[i], poly[i + 1]
        s += math.hypot(b[0] - a[0], b[1] - a[1])
    return s


def bbox_xyxy_from_contour(cnt: np.ndarray) -> tuple[int, int, int, int]:
    x, y, w, h = cv2.boundingRect(cnt)
    return (x, y, x + w, y + h)


def polyline_from_shifted_contour(
    cnt_full: np.ndarray,
    shape_kind: str,
    min_len_px: int,
) -> tuple[list[tuple[float, float]], tuple[int, int, int, int]]:
    """
    Centerline in the same pixel space as cnt_full (full rendered page).
    Use this after shift_contour so polylines cannot drift from the filled contour.
    """
    x, y, w, h = cv2.boundingRect(cnt_full)
    bbox = (x, y, x + w, y + h)

    if shape_kind == "diffuser":
        # Short horizontal tick (avoids tall vertical “marker” artifacts on wrong hits)
        xc = x + w / 2.0
        yc = y + h / 2.0
        r = max(6.0, min(w, h) * 0.42)
        return [(xc - r, yc), (xc + r, yc)], bbox

    sk_poly = skeleton_polyline_from_contour(cnt_full)
    if sk_poly is not None and _polyline_length(sk_poly) >= max(10.0, min_len_px * 0.52):
        return sk_poly, bbox

    poly, _ = contour_oriented_centerline(cnt_full)
    return poly, bbox


def _polyline_for_candidate(
    c: DuctCandidate, min_len_px: int
) -> tuple[list[tuple[float, float]], tuple[int, int, int, int]]:
    x, y, bw, bh = cv2.boundingRect(c.contour)
    bbox = (x, y, x + bw, y + bh)

    if c.kind == "diffuser":
        xc = x + bw / 2.0
        yc = y + bh / 2.0
        r = max(6.0, min(bw, bh) * 0.42)
        poly = [(xc - r, yc), (xc + r, yc)]
        return poly, bbox

    sk_poly = skeleton_polyline_from_contour(c.contour)
    if sk_poly is not None and _polyline_length(sk_poly) >= max(10.0, min_len_px * 0.52):
        return sk_poly, bbox

    poly, _ = contour_oriented_centerline(c.contour)
    return poly, bbox


def build_segments(
    candidates: list[DuctCandidate], page_number: int, min_len_px: int
) -> list[tuple[SegmentModel, np.ndarray]]:
    segments: list[tuple[SegmentModel, np.ndarray]] = []
    for i, c in enumerate(candidates):
        poly, bbox = _polyline_for_candidate(c, min_len_px)
        min_need = min_len_px * (0.32 if c.kind == "diffuser" else 1.0)
        if _polyline_length(poly) < min_need:
            continue
        seg_type = "supply" if i % 2 == 0 else "return"
        seg = SegmentModel(
            segment_id=f"D-{i+1:03d}",
            page_number=page_number,
            polyline=[(float(p[0]), float(p[1])) for p in poly],
            bbox=bbox,
            shape=c.kind,
            segment_type=seg_type,
            confidence=min(0.99, max(0.35, c.raw_confidence)),
        )
        segments.append((seg, c.contour.copy()))
    return segments


def shift_contour(cnt: np.ndarray, offset_x: int, offset_y: int) -> np.ndarray:
    """Shift contour to full-page coordinates; supports (N,1,2) or (N,2) from OpenCV."""
    pts = np.asarray(cnt, dtype=np.float32).reshape(-1, 2)
    pts[:, 0] += offset_x
    pts[:, 1] += offset_y
    return pts.astype(np.int32).reshape(-1, 1, 2)


def bbox_to_full_image(
    bbox: tuple[int, int, int, int], offset_x: int, offset_y: int
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    return (x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y)


def polyline_to_full_image(
    poly: list[tuple[float, float]], offset_x: int, offset_y: int
) -> list[tuple[float, float]]:
    return [(p[0] + offset_x, p[1] + offset_y) for p in poly]


def dumps_polyline(poly: list[tuple[float, float]]) -> str:
    return json.dumps([[p[0], p[1]] for p in poly])
