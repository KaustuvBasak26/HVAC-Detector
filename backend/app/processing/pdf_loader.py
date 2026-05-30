from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class PdfInfo:
    page_count: int
    page_width_pt: list[float]
    page_height_pt: list[float]


def validate_and_open(path: Path) -> fitz.Document:
    doc = fitz.open(path)
    if doc.page_count < 1:
        doc.close()
        raise ValueError("invalid_pdf")
    return doc


def get_pdf_info(doc: fitz.Document) -> PdfInfo:
    w, h = [], []
    for i in range(doc.page_count):
        r = doc[i].rect
        w.append(float(r.width))
        h.append(float(r.height))
    return PdfInfo(page_count=doc.page_count, page_width_pt=w, page_height_pt=h)
