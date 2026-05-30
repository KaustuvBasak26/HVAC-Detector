import re
from dataclasses import dataclass

from app.processing.text_extractor import TextBlock


@dataclass
class ScaleInfo:
    feet_per_pixel: float | None
    scale_text: str | None
    source: str


def _parse_scale_from_string(s: str) -> float | None:
    """
    Return feet per inch of drawing (paper) if pattern matches common architectural scales.
    E.g. 1/4\" = 1'-0\" -> 1 foot per 0.25 inch on drawing => 4 feet per inch on drawing.
    """
    s_norm = s.replace("′", "'").replace("’", "'")
    # 1/4" = 1'-0" or 1/4 = 1'-0
    m = re.search(
        r"(\d+)\s*/\s*(\d+)\s*\"?\s*=\s*(\d+)\s*['\u2032]?\s*[-]?\s*(\d+)?",
        s_norm,
        re.I,
    )
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        ft_whole = int(m.group(3))
        inches_part = int(m.group(4) or 0)
        drawing_inches = num / max(den, 1)
        real_feet = ft_whole + inches_part / 12.0
        if drawing_inches > 0:
            return real_feet / drawing_inches
    m2 = re.search(r"(\d+)\s*=\s*(\d+)", s_norm)
    if m2:
        a, b = int(m2.group(1)), int(m2.group(2))
        if a > 0 and b > 0 and a < 100 and b < 200:
            return b / a
    return None


def detect_scale(blocks: list[TextBlock], dpi: float) -> ScaleInfo:
    combined = " ".join(b.text for b in blocks)
    for b in blocks:
        for line in re.split(r"[\n\r]+", b.text):
            fpi = _parse_scale_from_string(line.strip())
            if fpi is not None:
                feet_per_pixel = fpi / dpi
                return ScaleInfo(
                    feet_per_pixel=feet_per_pixel, scale_text=line.strip(), source="text"
                )
    fpi = _parse_scale_from_string(combined)
    if fpi is not None:
        return ScaleInfo(feet_per_pixel=fpi / dpi, scale_text=combined[:120], source="text_combined")
    return ScaleInfo(feet_per_pixel=None, scale_text=None, source="none")
