import math

from app.processing.dimension_parser import ParsedDimension, find_dimension_candidates, parse_dimension_text
from app.processing.segment_builder import SegmentModel
from app.processing.text_extractor import TextBlock


def _seg_reference_point(seg: SegmentModel) -> tuple[float, float]:
    x0, y0, x1, y1 = seg.bbox
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _text_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def associate_labels(
    segments: list[SegmentModel],
    text_blocks: list[TextBlock],
    max_dist: float | None = None,
    img_w: int = 0,
    img_h: int = 0,
) -> dict[str, tuple[ParsedDimension | None, float]]:
    """
    Map segment_id -> (parsed dimension or None, confidence).
    """
    if max_dist is None:
        if img_w > 0 and img_h > 0:
            max_dist = max(520.0, min(1400.0, 0.12 * float(max(img_w, img_h))))
        else:
            max_dist = 680.0

    dim_blocks: list[tuple[TextBlock, ParsedDimension]] = []
    for tb in text_blocks:
        p = parse_dimension_text(tb.text)
        if p:
            dim_blocks.append((tb, p))
        elif len(tb.text) <= 200:
            # Avoid harvesting many numeric tokens from long spec / note paragraphs
            for cand in find_dimension_candidates(tb.text):
                dim_blocks.append((tb, cand))

    out: dict[str, tuple[ParsedDimension | None, float]] = {}
    for seg in segments:
        ref = _seg_reference_point(seg)
        best: tuple[ParsedDimension | None, float] = (None, 0.0)
        for tb, dim in dim_blocks:
            tc = _text_center(tb.bbox)
            d = _dist(ref, tc)
            if d > max_dist:
                continue
            conf = max(0.2, 1.0 - d / max_dist) * 0.85
            if conf > best[1]:
                best = (dim, conf)
        if best[0] is None:
            out[seg.segment_id] = (None, seg.confidence * 0.5)
        else:
            out[seg.segment_id] = (best[0], min(0.99, (best[1] + seg.confidence) / 2))
    return out
