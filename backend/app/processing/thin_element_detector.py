"""
Thin-line HVAC elements (flexible duct strokes) only.

Heuristic “diffuser / round symbol” hits matched grid bubbles, title graphics, and sheet
edges — producing wrong bboxes and vertical marker artifacts. Those classes are disabled
until we have a dedicated symbol detector.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from app.processing.duct_detector import (
    DuctCandidate,
    _reject_bottom_strip_artifact,
    _reject_top_strip_artifact,
)


def _circularity(area: float, perim: float) -> float:
    if perim <= 1e-6:
        return 0.0
    return float(4.0 * math.pi * area / (perim * perim))


def detect_thin_and_symbol_candidates(plan_bgr: np.ndarray) -> list[DuctCandidate]:
    gray = cv2.cvtColor(plan_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    blur = cv2.GaussianBlur(gray, (3, 3), 0)

    k_bh = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    blackhat = cv2.morphologyEx(blur, cv2.MORPH_BLACKHAT, k_bh)
    _, m_bh = cv2.threshold(blackhat, 8, 255, cv2.THRESH_BINARY)
    edges = cv2.Canny(blur, 35, 95)
    fused = cv2.bitwise_or(m_bh, edges)
    fused = cv2.dilate(fused, np.ones((2, 2), np.uint8), iterations=1)
    fused = cv2.morphologyEx(fused, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(fused, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total = float(h * w)
    out: list[DuctCandidate] = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 70 or area > total * 0.009:
            continue
        x, y, cw, ch = cv2.boundingRect(cnt)
        bb = (x, y, x + cw, y + ch)
        if _reject_top_strip_artifact(bb, w, h) or _reject_bottom_strip_artifact(bb, w, h):
            continue
        # Ignore blobs hugging plan ROI edges (borders / column lines)
        m = 0.03 * min(w, h)
        if x < m or y < m or (w - x - cw) < m or (h - y - ch) < m:
            continue
        per = cv2.arcLength(cnt, True)
        circ = _circularity(area, per)
        ar = cw / max(ch, 1)
        elong = max(ar, 1.0 / max(ar, 1e-6))
        tortuosity = per / max(math.sqrt(area), 1.0)

        # Skip near-circular blobs (diffusers / bubbles) — not modeled here
        if circ > 0.68 and elong < 2.2:
            continue

        # Flex only: must be visibly elongated and tortuous (wavy / fine run)
        if elong < 3.0 or tortuosity < 5.5:
            continue
        if max(cw, ch) < 110:
            continue
        if min(cw, ch) < 6:
            continue

        conf = min(0.78, 0.44 + min(per / 240.0, 0.3))

        if ar > 100 or ar < 1 / 100:
            continue

        out.append(
            DuctCandidate(
                contour=cnt,
                bbox=(x, y, x + cw, y + ch),
                raw_confidence=float(conf),
                kind="flex",
            )
        )

    out.sort(key=lambda c: c.raw_confidence, reverse=True)
    return out[:200]
