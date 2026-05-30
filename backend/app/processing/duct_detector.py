from dataclasses import dataclass

import cv2
import numpy as np

from app.processing.corridor_map import corridor_ridge_mask


@dataclass
class DuctCandidate:
    contour: np.ndarray
    bbox: tuple[int, int, int, int]
    raw_confidence: float
    kind: str = "rectangular"  # rectangular | flex | round | diffuser


def _close_axis(th: np.ndarray, h_len: int, v_len: int) -> np.ndarray:
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 2))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, v_len))
    h_close = cv2.morphologyEx(th, cv2.MORPH_CLOSE, h_kernel, iterations=1)
    v_close = cv2.morphologyEx(th, cv2.MORPH_CLOSE, v_kernel, iterations=1)
    return cv2.bitwise_or(h_close, v_close)


def _prepare_mask_otsu(gray: np.ndarray) -> np.ndarray:
    """
    Global Otsu on blurred gray — good when adaptive threshold merges the whole floor into
    one blob (common on light-gray MEP backgrounds). Produces many small–medium regions.
    """
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, k, iterations=1)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, k, iterations=1)
    return th


def _prepare_mask(gray: np.ndarray) -> np.ndarray:
    """
    Two-pass binarization + closing: long kernels catch mains, shorter kernels catch branches
    and thinner runs (e.g. round / flex adjacent to mains).
    """
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    # Coarse: stable on noisy backgrounds
    th1 = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 5
    )
    m1 = _close_axis(th1, 19, 19)
    # Fine: smaller blocks + shorter closing to reconnect short tees / branches
    th2 = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4
    )
    m2 = _close_axis(th2, 11, 11)
    merged = cv2.bitwise_or(m1, m2)
    merged = cv2.morphologyEx(merged, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    return merged


def _reject_top_strip_artifact(
    bbox: tuple[int, int, int, int], plan_w: int, plan_h: int
) -> bool:
    """Grid / border hairlines along the top of the plan crop."""
    x0, y0, x1, y1 = bbox
    cw, ch = x1 - x0, y1 - y0
    cy = 0.5 * (y0 + y1)
    if cy < plan_h * 0.035 and ch < plan_h * 0.022 and cw > plan_w * 0.22:
        return True
    if cy < plan_h * 0.028 and ch <= 10 and cw > plan_w * 0.18:
        return True
    return False


def _reject_bottom_strip_artifact(
    bbox: tuple[int, int, int, int], plan_w: int, plan_h: int
) -> bool:
    """Dimension / grid ticks along the bottom of the plan crop (above notes)."""
    x0, y0, x1, y1 = bbox
    cw, ch = x1 - x0, y1 - y0
    cy = 0.5 * (y0 + y1)
    if cy > plan_h * 0.965 and ch < plan_h * 0.028 and cw > plan_w * 0.22:
        return True
    if cy > plan_h * 0.972 and ch <= 12 and cw > plan_w * 0.18:
        return True
    return False


def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0, ix1 - ix0), max(0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / max(ua, 1)


def _dedupe_candidates(cands: list[DuctCandidate], iou_keep: float = 0.72) -> list[DuctCandidate]:
    cands = sorted(cands, key=lambda c: c.raw_confidence, reverse=True)
    kept: list[DuctCandidate] = []
    for c in cands:
        if any(_bbox_iou(c.bbox, k.bbox) > iou_keep for k in kept):
            continue
        kept.append(c)
    return kept


def _candidates_from_mask(
    mask: np.ndarray,
    min_area: int,
    max_area_ratio: float,
    conf_scale: float,
    *,
    elong_area_max: float | None = None,
    elong_min: float = 1.52,
) -> list[DuctCandidate]:
    h, w = mask.shape[:2]
    total = float(h * w)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: list[DuctCandidate] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > total * max_area_ratio:
            continue
        x, y, cw, ch = cv2.boundingRect(cnt)
        bb = (x, y, x + cw, y + ch)
        if _reject_top_strip_artifact(bb, w, h) or _reject_bottom_strip_artifact(bb, w, h):
            continue
        ar = cw / max(ch, 1)
        if ar > 100 or ar < 1 / 100:
            continue
        if cw > w * 0.92 and ch < max(5.0, h * 0.025):
            continue
        if ch > h * 0.92 and cw < max(5.0, w * 0.025):
            continue
        if cw > w * 0.96 or ch > h * 0.96:
            continue
        if elong_area_max is not None and area <= elong_area_max:
            elong = max(cw / max(ch, 1), ch / max(cw, 1))
            if elong < elong_min:
                continue
        conf = (
            min(1.0, area / 4200.0)
            * (1.0 - abs(np.log(max(ar, 1 / max(ar, 1e-6))) / 8))
            * conf_scale
        )
        out.append(
            DuctCandidate(
                contour=cnt,
                bbox=(x, y, x + cw, y + ch),
                raw_confidence=float(conf),
                kind="rectangular",
            )
        )
    return out


def _candidates_from_corridor_ridge(
    gray: np.ndarray,
    *,
    ridge_min_dt: float,
    ridge_max_dt_frac: float,
    min_area: int,
    max_area_ratio: float,
) -> list[DuctCandidate]:
    """
    Medial pixels between parallel ink lines — strong prior for rectangular MEP duct runs
    (matches double-line markup references) with little response on single-width grids.
    """
    h, w = gray.shape[:2]
    cap = float(min(h, w)) * float(ridge_max_dt_frac)
    cap = max(ridge_min_dt + 2.0, cap)
    mask = corridor_ridge_mask(gray, min_dt=float(ridge_min_dt), max_dt=cap, close_ksize=3)
    return _candidates_from_mask(
        mask,
        int(min_area),
        float(max_area_ratio),
        conf_scale=0.88,
        elong_area_max=None,
        elong_min=1.32,
    )


def detect_duct_candidates(
    plan_bgr: np.ndarray,
    min_area: int = 280,
    max_area_ratio: float = 0.18,
    use_otsu_secondary: bool = True,
    otsu_max_area_ratio: float = 0.034,
    otsu_min_area: int = 200,
    candidate_cap: int = 1200,
    otsu_elong_area_max: float | None = 8500.0,
    otsu_elong_min: float = 1.52,
    use_corridor_ridge: bool = True,
    corridor_ridge_min_dt: float = 1.42,
    corridor_ridge_max_dt_frac: float = 0.055,
    corridor_ridge_min_area: int = 300,
    corridor_ridge_max_area_ratio: float = 0.12,
) -> list[DuctCandidate]:
    from app.processing.thin_element_detector import detect_thin_and_symbol_candidates

    gray = cv2.cvtColor(plan_bgr, cv2.COLOR_BGR2GRAY)
    candidates: list[DuctCandidate] = []
    candidates.extend(
        _candidates_from_mask(_prepare_mask(gray), min_area, max_area_ratio, conf_scale=1.0)
    )
    if use_otsu_secondary:
        candidates.extend(
            _candidates_from_mask(
                _prepare_mask_otsu(gray),
                min(otsu_min_area, min_area),
                otsu_max_area_ratio,
                conf_scale=0.94,
                elong_area_max=otsu_elong_area_max,
                elong_min=otsu_elong_min,
            )
        )
    if use_corridor_ridge:
        candidates.extend(
            _candidates_from_corridor_ridge(
                gray,
                ridge_min_dt=float(corridor_ridge_min_dt),
                ridge_max_dt_frac=float(corridor_ridge_max_dt_frac),
                min_area=int(corridor_ridge_min_area),
                max_area_ratio=float(corridor_ridge_max_area_ratio),
            )
        )
    candidates.extend(detect_thin_and_symbol_candidates(plan_bgr))
    candidates = _dedupe_candidates(candidates, iou_keep=0.58)
    candidates.sort(key=lambda c: c.raw_confidence, reverse=True)
    return candidates[: int(max(100, candidate_cap))]
