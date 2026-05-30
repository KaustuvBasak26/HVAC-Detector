import re
from dataclasses import dataclass


@dataclass
class ParsedDimension:
    raw: str
    width_in: float | None
    height_in: float | None
    diameter_in: float | None


_RECT_PATTERNS = [
    re.compile(r"^(\d+)\s*[xX×]\s*(\d+)$"),
    re.compile(r"^(\d+)\s*/\s*(\d+)$"),
]

# Duct sizes embedded in longer labels (e.g. "SUPPLY 24x12", CAD callouts `18" x 6"`, `12 x 8`)
_RECT_IN_TEXT = re.compile(
    r"(?<![\d.])(\d{1,3})\s*[\"″′]?\s*[xX×]\s*(\d{1,3})\s*[\"″′]?(?!\d)"
)

_DIA_PATTERNS = [
    re.compile(r"^[Øø]\s*(\d+(?:\.\d+)?)$"),
    re.compile(r"^(\d+(?:\.\d+)?)\s*(?:DIA|Dia|dia)\.?$"),
    re.compile(r"^(\d+(?:\.\d+)?)\s*\"?\s*ø$", re.I),
]

# "12Ø", '12"Ø', "Ø12" in callouts
_DIA_LEAD = re.compile(r"(?<![\d.])(\d{1,3})\s*[\"″′']?\s*[Øø]")
_DIA_SYM = re.compile(r"(?<![\d.])[Øø]\s*(\d{1,3}(?:\.\d+)?)")


def parse_dimension_text(text: str) -> ParsedDimension | None:
    t = text.strip()
    if not t:
        return None
    m_embed = _RECT_IN_TEXT.search(t)
    if m_embed:
        a, b = float(m_embed.group(1)), float(m_embed.group(2))
        return ParsedDimension(raw=m_embed.group(0).strip(), width_in=a, height_in=b, diameter_in=None)
    m_dia = _DIA_LEAD.search(t) or _DIA_SYM.search(t)
    if m_dia:
        d_raw = m_dia.group(0).strip()
        d = float(m_dia.group(1))
        return ParsedDimension(raw=d_raw, width_in=None, height_in=None, diameter_in=d)
    for pat in _RECT_PATTERNS:
        m = pat.match(t)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            return ParsedDimension(raw=t, width_in=a, height_in=b, diameter_in=None)
    for pat in _DIA_PATTERNS:
        m = pat.match(t)
        if m:
            d = float(m.group(1))
            return ParsedDimension(raw=t, width_in=None, height_in=None, diameter_in=d)
    return None


def find_dimension_candidates(text: str) -> list[ParsedDimension]:
    """Scan longer strings for embedded size tokens."""
    out: list[ParsedDimension] = []
    for m in _RECT_IN_TEXT.finditer(text):
        a, b = float(m.group(1)), float(m.group(2))
        out.append(
            ParsedDimension(raw=m.group(0).strip(), width_in=a, height_in=b, diameter_in=None)
        )
    for m in _DIA_LEAD.finditer(text):
        out.append(
            ParsedDimension(
                raw=m.group(0).strip(),
                width_in=None,
                height_in=None,
                diameter_in=float(m.group(1)),
            )
        )
    for m in _DIA_SYM.finditer(text):
        out.append(
            ParsedDimension(
                raw=m.group(0).strip(),
                width_in=None,
                height_in=None,
                diameter_in=float(m.group(1)),
            )
        )
    for token in re.split(r"[\s,;]+", text):
        p = parse_dimension_text(token)
        if p and p.raw not in {x.raw for x in out}:
            out.append(p)
    return out
