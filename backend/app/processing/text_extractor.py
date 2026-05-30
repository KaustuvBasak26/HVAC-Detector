from dataclasses import dataclass

import fitz


@dataclass
class TextBlock:
    text: str
    bbox: tuple[float, float, float, float]
    page_number: int


def _merge_adjacent_words_on_line(blocks: list[TextBlock], y_tol: float, max_gap: float) -> list[TextBlock]:
    """Join PDF word fragments on one line into one string (e.g. 24 + x + 12 -> 24x12)."""
    if len(blocks) < 2:
        return []
    ordered = sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0]))
    merged: list[TextBlock] = []
    row: list[TextBlock] = [ordered[0]]
    for w in ordered[1:]:
        prev = row[-1]
        y_close = abs(w.bbox[1] - prev.bbox[1]) <= y_tol and abs(w.bbox[3] - prev.bbox[3]) <= y_tol * 2
        gap = w.bbox[0] - prev.bbox[2]
        if y_close and -2 <= gap <= max_gap:
            row.append(w)
        else:
            if len(row) >= 2:
                merged.append(_combine_row(row))
            row = [w]
    if len(row) >= 2:
        merged.append(_combine_row(row))
    return merged


def _combine_row(row: list[TextBlock]) -> TextBlock:
    row = sorted(row, key=lambda b: b.bbox[0])
    text = "".join(b.text for b in row)
    x0 = min(b.bbox[0] for b in row)
    y0 = min(b.bbox[1] for b in row)
    x1 = max(b.bbox[2] for b in row)
    y1 = max(b.bbox[3] for b in row)
    return TextBlock(text=text, bbox=(x0, y0, x1, y1), page_number=row[0].page_number)


def extract_words_scaled(
    doc: fitz.Document, page_index: int, scale_x: float, scale_y: float
) -> list[TextBlock]:
    page = doc[page_index]
    words = page.get_text("words")
    out: list[TextBlock] = []
    heights: list[float] = []
    for w in words:
        x0, y0, x1, y1, text, *_ = w
        if not text or not text.strip():
            continue
        x0s, y0s, x1s, y1s = x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y
        out.append(
            TextBlock(
                text=text.strip(),
                bbox=(x0s, y0s, x1s, y1s),
                page_number=page_index + 1,
            )
        )
        heights.append(y1s - y0s)
    med_h = sorted(heights)[len(heights) // 2] if heights else 10.0
    y_tol = max(5.0, med_h * 0.85)
    max_gap = max(24.0, med_h * 4.0)
    merged = _merge_adjacent_words_on_line(out, y_tol=y_tol, max_gap=max_gap)
    return out + merged
