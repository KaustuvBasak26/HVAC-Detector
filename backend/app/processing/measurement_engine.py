import math

from app.processing.scale_detector import ScaleInfo
from app.processing.segment_builder import SegmentModel


def polyline_length_px(poly: list[tuple[float, float]]) -> float:
    s = 0.0
    for i in range(len(poly) - 1):
        a, b = poly[i], poly[i + 1]
        s += math.hypot(b[0] - a[0], b[1] - a[1])
    return s


def measure_segment_length_ft(
    seg: SegmentModel, scale: ScaleInfo, default_ft_per_px: float | None
) -> tuple[float | None, str]:
    px = polyline_length_px(seg.polyline)
    fpp = scale.feet_per_pixel
    if fpp is None:
        fpp = default_ft_per_px
    if fpp is None:
        return None, "scale_unknown"
    return round(px * fpp, 2), "centerline"
