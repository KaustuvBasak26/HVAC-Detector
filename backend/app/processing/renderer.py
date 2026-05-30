from dataclasses import dataclass

import fitz
import numpy as np


@dataclass
class PageRender:
    image_bgr: np.ndarray
    dpi: int
    scale_x: float
    scale_y: float
    page_width_pt: float
    page_height_pt: float


def render_page(doc: fitz.Document, page_index: int, dpi: int) -> PageRender:
    page = doc[page_index]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    bgr = img[:, :, ::-1].copy()
    r = page.rect
    return PageRender(
        image_bgr=bgr,
        dpi=dpi,
        scale_x=float(zoom),
        scale_y=float(zoom),
        page_width_pt=float(r.width),
        page_height_pt=float(r.height),
    )
