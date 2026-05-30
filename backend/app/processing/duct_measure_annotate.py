"""
Duct segments from a centerline mask, drawing-text notes, geometric lengths, and annotations.

On-plan D-* tags are drawn at the **polyline midpoint** of each centerline (Pillow).
The bottom-left **HVAC DUCT MEASURE** schedule scales with raster size so it stays
visible on high-DPI renders and clear of the right-hand title block.
Coordinates are in **rendered pixel space** (same as ``render_page`` / mask).
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.processing.dimension_parser import ParsedDimension, find_dimension_candidates, parse_dimension_text
from app.processing.segment_builder import SegmentModel

# --- Legend overlay (matches hvac_duct_measure_legend_enhanced.py) ---
LABEL_BLUE = (0, 60, 220)
LABEL_OUTLINE = (0, 80, 255)


@dataclass
class TextAnnotation:
    text: str
    cx: float
    cy: float
    bbox: tuple[float, float, float, float]


def ft_to_arch(feet: float) -> str:
    total_inches = max(0, int(round(feet * 12)))
    ft = total_inches // 12
    inch = total_inches % 12
    return f"{ft}'-{inch}\""


def parse_arch_length(text: str) -> float | None:
    m = re.search(r"(\d+)\s*'\s*(?:-|–)?\s*(\d+)?\s*\"?", text)
    if not m:
        return None
    ft = int(m.group(1))
    inch = int(m.group(2) or 0)
    return ft + inch / 12.0


def extract_line_annotations_pixel(page: fitz.Page, scale_x: float, scale_y: float) -> list[TextAnnotation]:
    """Rebuild PDF text lines in pixel coordinates (same basis as ``extract_words_scaled``)."""
    words = page.get_text("words")
    lines: dict[tuple[int, int], list] = {}
    for w in words:
        x0, y0, x1, y1, text, block, line, _word_no = w
        lines.setdefault((block, line), []).append(w)

    out: list[TextAnnotation] = []
    for line_words in lines.values():
        line_words.sort(key=lambda v: v[0])
        text = " ".join(str(w[4]) for w in line_words).strip()
        if not text:
            continue
        x0 = min(float(w[0]) for w in line_words)
        y0 = min(float(w[1]) for w in line_words)
        x1 = max(float(w[2]) for w in line_words)
        y1 = max(float(w[3]) for w in line_words)
        cx = (x0 + x1) / 2 * scale_x
        cy = (y0 + y1) / 2 * scale_y
        bbox = (x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y)
        out.append(TextAnnotation(text=text, cx=cx, cy=cy, bbox=bbox))
    return out


def extract_length_notes(annotations: Sequence[TextAnnotation]) -> list[TextAnnotation]:
    notes: list[TextAnnotation] = []

    for ann in annotations:
        txt = ann.text.replace(" – ", " - ")
        if re.search(r"\bC\d{2}\b", txt) and parse_arch_length(txt):
            notes.append(ann)

    tag_items = [a for a in annotations if re.fullmatch(r"C\d{2}", a.text.strip())]
    len_items = [a for a in annotations if parse_arch_length(a.text)]
    existing = {n.text for n in notes}
    for tag in tag_items:
        nearby = [
            a for a in len_items
            if abs(a.cy - tag.cy) < 8 and abs(a.cx - tag.cx) < 80
        ]
        if not nearby:
            nearby = [a for a in len_items if math.hypot(a.cx - tag.cx, a.cy - tag.cy) < 90]
        if not nearby:
            continue
        length_ann = min(nearby, key=lambda a: math.hypot(a.cx - tag.cx, a.cy - tag.cy))
        combined = f"{tag.text} {length_ann.text}"
        if combined in existing:
            continue
        x0 = min(tag.bbox[0], length_ann.bbox[0])
        y0 = min(tag.bbox[1], length_ann.bbox[1])
        x1 = max(tag.bbox[2], length_ann.bbox[2])
        y1 = max(tag.bbox[3], length_ann.bbox[3])
        notes.append(
            TextAnnotation(
                combined,
                (tag.cx + length_ann.cx) / 2,
                (tag.cy + length_ann.cy) / 2,
                (x0, y0, x1, y1),
            )
        )
        existing.add(combined)

    return notes


def nearest_note_text(
    cx: float, cy: float, notes: Sequence[TextAnnotation], max_dist: float = 500
) -> str:
    if not notes:
        return ""
    best = min(notes, key=lambda a: math.hypot(a.cx - cx, a.cy - cy))
    dist = math.hypot(best.cx - cx, best.cy - cy)
    return best.text if dist <= max_dist else ""


def extract_dimension_notes(annotations: Sequence[TextAnnotation]) -> list[TextAnnotation]:
    dims: list[TextAnnotation] = []
    dim_re = re.compile(
        r"\b\d{1,2}\s*(?:x|X|×)\s*\d{1,2}\b|\b\d{1,2}\s*(?:\"|in|IN|Ø|ø)\b"
    )
    for ann in annotations:
        if dim_re.search(ann.text):
            dims.append(ann)
    return dims


def infer_dimension(
    cx: float,
    cy: float,
    orientation: str,
    dimension_notes: Sequence[TextAnnotation],
    page_width: int,
    page_height: int,
) -> str:
    if dimension_notes:
        best = min(dimension_notes, key=lambda a: math.hypot(a.cx - cx, a.cy - cy))
        if math.hypot(best.cx - cx, best.cy - cy) < 180:
            return best.text

    if cx > page_width * 0.47:
        return '14" dia / branch'
    if cy < page_height * 0.29:
        return '18" main'
    if page_width * 0.25 < cx < page_width * 0.43 and page_height * 0.29 < cy < page_height * 0.44:
        return '12" duct'
    if cx < page_width * 0.28:
        return '12" branch'
    if orientation == "vertical":
        return '12" drop/riser'
    return "size from plan note"


def classify_orientation(w: int, h: int) -> str:
    if w > h * 2.5:
        return "horizontal"
    if h > w * 2.5:
        return "vertical"
    return "angled"


def _dimension_to_parsed(dim_str: str) -> tuple[ParsedDimension | None, float]:
    p = parse_dimension_text(dim_str)
    if p:
        return p, 0.82
    cand = find_dimension_candidates(dim_str)
    if cand:
        return cand[0], 0.68
    return (
        ParsedDimension(raw=dim_str, width_in=None, height_in=None, diameter_in=None),
        0.55,
    )


def feet_per_render_pixel(page: fitz.Page, render_width: int, scale_feet_per_drawing_inch: float) -> float:
    """PDF points per raster pixel → feet per pixel (architectural scale convention)."""
    pdf_points_per_px = float(page.rect.width) / max(1, render_width)
    return (pdf_points_per_px / 72.0) * float(scale_feet_per_drawing_inch)


def segments_from_centerline_mask(
    centerline_mask: np.ndarray,
    page: fitz.Page,
    line_annotations: Sequence[TextAnnotation],
    page_number: int,
    scale_feet_per_drawing_inch: float,
) -> tuple[
    list[SegmentModel],
    dict[str, tuple[ParsedDimension | None, float]],
    dict[str, tuple[float | None, str]],
    dict[str, str],
]:
    """
    Connected components on ``centerline_mask`` (8-connectivity), with labels/lengths
    matching the exporter contract.

    The fourth return value maps segment_id → nearest extracted PDF length note (Cxx …), if any.
    """
    num, _labels, stats, centroids = cv2.connectedComponentsWithStats(
        centerline_mask, connectivity=8
    )
    render_h, render_w = centerline_mask.shape
    fpp = feet_per_render_pixel(page, render_w, scale_feet_per_drawing_inch)

    length_notes = extract_length_notes(line_annotations)
    dimension_notes = extract_dimension_notes(line_annotations)

    labels: dict[str, tuple[ParsedDimension | None, float]] = {}
    lengths: dict[str, tuple[float | None, str]] = {}
    pdf_notes: dict[str, str] = {}

    seg_list: list[SegmentModel] = []
    idx = 1
    for i in range(1, num):
        x, y, w, h, area = [int(v) for v in stats[i]]
        if area < 60:
            continue
        orientation = classify_orientation(w, h)
        if orientation == "horizontal":
            px_len = float(w)
        elif orientation == "vertical":
            px_len = float(h)
        else:
            px_len = float(math.hypot(w, h))
        if px_len < 30:
            continue

        cx, cy = float(centroids[i][0]), float(centroids[i][1])
        dim_str = infer_dimension(
            cx, cy, orientation, dimension_notes, render_w, render_h
        )
        nearest = nearest_note_text(cx, cy, length_notes, max_dist=650)

        if orientation == "horizontal":
            poly = [(float(x), float(y + h / 2)), (float(x + w), float(y + h / 2))]
        elif orientation == "vertical":
            poly = [(float(x + w / 2), float(y)), (float(x + w / 2), float(y + h))]
        else:
            poly = [(float(x), float(y)), (float(x + w), float(y + h))]

        shape = (
            "rectangular" if orientation in ("horizontal", "vertical") else "flex"
        )
        sid = f"D-{idx:03d}"
        drawing_ft = px_len * fpp
        # segment_type encodes note in exporter as type field; keep supply/return for parity
        st = "supply" if idx % 2 == 1 else "return"

        seg = SegmentModel(
            segment_id=sid,
            page_number=page_number,
            polyline=poly,
            bbox=(x, y, x + w, y + h),
            shape=shape,
            segment_type=st,
            confidence=0.72,
            centroid_x=cx,
            centroid_y=cy,
            label_orientation=orientation,
        )
        seg_list.append(seg)

        parsed, conf = _dimension_to_parsed(dim_str)
        labels[sid] = (parsed, conf)
        lengths[sid] = (round(drawing_ft, 2), "centerline_mask_geom")
        pdf_notes[sid] = nearest

        idx += 1

    seg_list.sort(key=lambda s: (s.bbox[1], s.bbox[0]))
    return seg_list, labels, lengths, pdf_notes


def short_dim(dim: str, max_len: int = 18) -> str:
    dim = (dim or "unknown").replace("\n", " ").strip()
    return dim if len(dim) <= max_len else dim[: max_len - 1] + "…"


def _polyline_midpoint(poly: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Geometric midpoint along the duct centerline (stable label anchor)."""
    pts = list(poly)
    if not pts:
        return 0.0, 0.0
    if len(pts) < 2:
        return float(pts[0][0]), float(pts[0][1])
    segs: list[float] = []
    total = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append(d)
        total += d
    if total < 1e-6:
        mi = len(pts) // 2
        return float(pts[mi][0]), float(pts[mi][1])
    target = total * 0.5
    acc = 0.0
    idx = 0
    for i, d in enumerate(segs):
        if acc + d >= target:
            idx = i
            break
        acc += d
    t = (target - acc) / max(segs[idx], 1e-6)
    a, b = pts[idx], pts[idx + 1]
    return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])


def _export_type_display(shape: str, dim_t: ParsedDimension | None) -> str:
    if dim_t and dim_t.diameter_in is not None:
        return "Round"
    if dim_t and dim_t.width_in is not None and dim_t.height_in is not None:
        return "Rect. duct"
    sh = (shape or "").lower()
    if sh == "flex":
        return "Flex"
    if sh == "diffuser":
        return "Diffuser"
    if sh == "rectangular":
        return "Rect. duct"
    return "Duct"


@dataclass(frozen=True)
class _LegendLayout:
    box_x: int
    box_y: int
    box_w: int
    box_h: int
    scale: float


def _compute_legend_layout(image_w: int, image_h: int) -> _LegendLayout:
    """Bottom-left legend band sized for the raster (title block stays on the right)."""
    sc = max(0.72, min(1.35, min(image_w, image_h) / 2200.0))
    margin_x = max(20, int(image_w * 0.018))
    margin_bottom = max(14, int(image_h * 0.012))
    box_h = max(int(260 * sc), min(int(image_h * 0.30), int(image_h * 0.34)))
    box_y = image_h - box_h - margin_bottom
    box_x = margin_x
    max_right = int(image_w * 0.58)
    box_w = max(420, min(int(1200 * sc), max(0, max_right - box_x)))
    return _LegendLayout(
        box_x=box_x,
        box_y=box_y,
        box_w=box_w,
        box_h=box_h,
        scale=sc,
    )


def split_rows(rows: Sequence[Any], max_rows_per_table: int = 11) -> list[list[Any]]:
    return [list(rows[i : i + max_rows_per_table]) for i in range(0, len(rows), max_rows_per_table)]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths: list[str] = []
    if sys.platform == "darwin":
        paths.extend(
            (
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
            )
        )
    paths.extend(
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        )
    )
    for path in paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=max(6, int(size)))
            except OSError:
                continue
    return ImageFont.load_default()


@dataclass
class _PillowLegendSegment:
    """Segment payload for Pillow drawing (plan tags + schedule rows)."""

    segment_id: str
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    label_anchor: tuple[float, float]
    orientation: str
    pixel_length: float
    drawing_length_ft: float
    dimension: str
    type_display: str
    nearest_note: str


def _segment_models_to_pillow_segments(
    segments: Sequence[SegmentModel],
    lengths: dict[str, tuple[float | None, str]],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    pdf_notes: dict[str, str],
) -> list[_PillowLegendSegment]:
    out: list[_PillowLegendSegment] = []
    for s in segments:
        x0, y0, x1, y1 = s.bbox
        w, h = x1 - x0, y1 - y0
        px_len = float(max(w, h))
        dim_t, _ = labels.get(s.segment_id, (None, 0.0))
        dim_str = dim_t.raw if dim_t else "?"
        lf, _ = lengths.get(s.segment_id, (None, ""))
        note = pdf_notes.get(s.segment_id, "") or ""
        cx = float(s.centroid_x) if s.centroid_x is not None else x0 + w / 2.0
        cy = float(s.centroid_y) if s.centroid_y is not None else y0 + h / 2.0
        orient = s.label_orientation or classify_orientation(w, h)
        if len(s.polyline) >= 2:
            px, py = _polyline_midpoint(s.polyline)
        else:
            px, py = cx, cy
        # Tall/wide CC boxes: bbox midline can sit away from the ink; centroid stays on the mask.
        if orient == "horizontal" and h > max(20, int(w * 0.42) + 6):
            ax, ay = float(px), float(cy)
        elif orient == "vertical" and w > max(20, int(h * 0.42) + 6):
            ax, ay = float(cx), float(py)
        else:
            ax, ay = float(px), float(py)
        type_disp = _export_type_display(s.shape, dim_t)
        out.append(
            _PillowLegendSegment(
                segment_id=s.segment_id,
                bbox=(x0, y0, w, h),
                centroid=(cx, cy),
                label_anchor=(ax, ay),
                orientation=orient,
                pixel_length=px_len,
                drawing_length_ft=float(lf or 0.0),
                dimension=dim_str,
                type_display=type_disp,
                nearest_note=note,
            )
        )
    return out


def _rects_overlap(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 < bx0 or ax0 > bx1 or ay1 < by0 or ay0 > by1)


def draw_segment_id_tag(
    draw: ImageDraw.ImageDraw,
    seg: _PillowLegendSegment,
    font: ImageFont.ImageFont,
    image_w: int,
    image_h: int,
    layout: _LegendLayout,
) -> None:
    """Place segment ID next to the duct anchor. Legend overlap is a small nudge only — never stack all tags."""
    mx, my = seg.label_anchor
    label = seg.segment_id
    tb0 = draw.textbbox((0, 0), label, font=font)
    tw, th = tb0[2] - tb0[0], tb0[3] - tb0[1]
    pad = max(2, int(2 * layout.scale))
    v_off = max(8, int(10 * layout.scale))
    h_off = max(6, int(8 * layout.scale))
    m = 6
    leg = (
        layout.box_x,
        layout.box_y,
        layout.box_x + layout.box_w,
        layout.box_y + layout.box_h,
    )

    o = seg.orientation
    if o == "horizontal":
        tx = int(mx - tw / 2)
        if tx < m:
            tx = int(mx + h_off)
        ty = int(my - th - v_off)
    elif o == "vertical":
        tx = int(mx + h_off)
        if tx + tw > image_w - m:
            tx = int(mx - tw - h_off)
        ty = int(my - th // 2)
    else:
        tx = int(mx + h_off // 2)
        ty = int(my - th - v_off)

    tx = max(m, min(tx, image_w - tw - m))
    ty = max(m, min(ty, image_h - th - m))

    def padded_bbox(tx_i: int, ty_i: int) -> tuple[int, int, int, int]:
        b = draw.textbbox((tx_i, ty_i), label, font=font)
        return (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)

    for _ in range(4):
        pr = padded_bbox(tx, ty)
        if not _rects_overlap(pr, leg):
            break
        shift = pr[3] - leg[1] + 8
        if shift > 0:
            ty = int(ty - shift)
        else:
            ty = int(ty - (v_off + th // 2))
        ty = max(m, ty)

    bbox = draw.textbbox((tx, ty), label, font=font)
    rect = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    draw.rectangle(rect, fill=(255, 255, 255), outline=LABEL_OUTLINE, width=1)
    draw.text((tx, ty), label, fill=LABEL_BLUE, font=font)


def draw_legend_table(
    draw: ImageDraw.ImageDraw,
    segments: Sequence[_PillowLegendSegment],
    annotations: Sequence[TextAnnotation],
    layout: _LegendLayout,
) -> None:
    """Bottom-left HVAC schedule (matches mechanical sheet-style layout)."""
    sc = layout.scale
    box_x, box_y, box_w, box_h = layout.box_x, layout.box_y, layout.box_w, layout.box_h

    title_font = load_font(int(14 * sc))
    header_font = load_font(int(10 * sc))
    row_font = load_font(int(9 * sc))
    note_font = load_font(int(8 * sc))

    rows = [s for s in segments if s.pixel_length >= 45]
    rows = sorted(rows, key=lambda s: (s.bbox[1], s.bbox[0]))

    pad = max(10, int(12 * sc))
    draw.rectangle(
        (box_x, box_y, box_x + box_w, box_y + box_h),
        fill=(255, 255, 255),
        outline=LABEL_OUTLINE,
        width=max(1, int(2 * min(sc, 1.0))),
    )
    title = "HVAC DUCT MEASURE - DETECTED CENTERLINES, DIMENSIONS, AND LENGTHS"
    draw.text((box_x + pad, box_y + int(10 * sc)), title, fill=LABEL_BLUE, font=title_font)
    draw.text(
        (box_x + pad, box_y + int(28 * sc)),
        "Blue lines = duct centerlines. IDs on plan match the schedule below.",
        fill=(0, 0, 0),
        font=note_font,
    )
    draw.text(
        (box_x + pad, box_y + int(44 * sc)),
        "Lengths use detected or default drawing scale; PCH column lists nearby PDF length notes when found.",
        fill=(0, 0, 0),
        font=note_font,
    )

    table_top = box_y + int(64 * sc)
    row_h = max(15, int(18 * sc))
    header_h = max(18, int(20 * sc))
    header_block = int(92 * sc)
    max_rows = min(11, max(1, (box_h - header_block) // row_h))
    groups = split_rows(rows, max_rows)
    if len(groups) > 2:
        rows = sorted(rows, key=lambda s: s.pixel_length, reverse=True)[: max_rows * 2]
        rows = sorted(rows, key=lambda s: (s.bbox[1], s.bbox[0]))
        groups = split_rows(rows, max_rows)

    group_w = (box_w - 2 * pad) // max(1, len(groups))
    col_fracs = [0.12, 0.20, 0.24, 0.18, 0.26]
    headers = ["ID", "Type", "Dimension", "Length", "PCH note"]

    for gi, group in enumerate(groups):
        gx = box_x + pad + gi * group_w
        gy = table_top
        gw = group_w - max(6, int(10 * sc))
        draw.rectangle((gx, gy, gx + gw, gy + header_h), fill=(245, 250, 255), outline=(0, 80, 255), width=1)

        col_x = [gx]
        accum = gx
        for frac in col_fracs[:-1]:
            accum += int(gw * frac)
            col_x.append(accum)
            draw.line((accum, gy, accum, gy + header_h + row_h * len(group)), fill=(0, 80, 255), width=1)
        col_x.append(gx + gw)

        for hi, header in enumerate(headers):
            draw.text((col_x[hi] + 3, gy + int(4 * sc)), header, fill=(0, 0, 0), font=header_font)

        for ri, seg in enumerate(group):
            ry = gy + header_h + ri * row_h
            draw.rectangle((gx, ry, gx + gw, ry + row_h), outline=(150, 190, 255), width=1)
            vals = [
                seg.segment_id,
                seg.type_display,
                short_dim(seg.dimension, 20),
                ft_to_arch(seg.drawing_length_ft),
                short_dim(seg.nearest_note, 22),
            ]
            for ci, val in enumerate(vals):
                draw.text((col_x[ci] + 3, ry + int(3 * sc)), val, fill=(0, 0, 0), font=row_font)

    length_notes: list[str] = []
    for n in extract_length_notes(annotations):
        if n.text not in length_notes:
            length_notes.append(n.text)

    foot_y = box_y + box_h - int(48 * sc)
    y_rule = foot_y - int(8 * sc)
    x0, x1 = box_x + pad, box_x + box_w - pad
    draw.line((x0, y_rule, x1, y_rule), fill=(0, 80, 255), width=1)
    draw.text((box_x + pad, foot_y), f"Segments listed: {len(rows)}", fill=(0, 0, 0), font=note_font)
    if length_notes:
        notes_text = "; ".join(length_notes[:7])
        if len(notes_text) > 130:
            notes_text = notes_text[:129] + "…"
        draw.text(
            (box_x + int(140 * sc), foot_y),
            f"Extracted notes: {notes_text}",
            fill=(0, 0, 0),
            font=note_font,
        )


def draw_annotations(
    image_rgb: np.ndarray,
    segments: Sequence[_PillowLegendSegment],
    annotations: Sequence[TextAnnotation],
    page_index: int = 0,
) -> np.ndarray:
    _ = page_index
    image = Image.fromarray(image_rgb)
    draw = ImageDraw.Draw(image)
    layout = _compute_legend_layout(image.width, image.height)
    id_font = load_font(int(10 * layout.scale))

    for seg in segments:
        if seg.pixel_length < 45:
            continue
        draw_segment_id_tag(draw, seg, id_font, image.width, image.height, layout)

    draw_legend_table(draw, segments, annotations, layout)

    return np.array(image)


def draw_legend_overlay_bgr(
    image_bgr: np.ndarray,
    segments: Sequence[SegmentModel],
    line_annotations: Sequence[TextAnnotation],
    lengths: dict[str, tuple[float | None, str]],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    pdf_notes: dict[str, str],
) -> np.ndarray:
    """BGR image → RGB → Pillow (reference script) → BGR."""
    pillow_segs = _segment_models_to_pillow_segments(segments, lengths, labels, pdf_notes)
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    marked = draw_annotations(rgb, pillow_segs, line_annotations)
    return cv2.cvtColor(marked.astype(np.uint8), cv2.COLOR_RGB2BGR)


def draw_measure_overlay_bgr(
    image_bgr: np.ndarray,
    segments: Sequence[SegmentModel],
    line_annotations: Sequence[TextAnnotation],
    lengths: dict[str, tuple[float | None, str]],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    pdf_notes: dict[str, str] | None = None,
) -> np.ndarray:
    """Backward-compatible name; delegates to :func:`draw_legend_overlay_bgr`."""
    return draw_legend_overlay_bgr(
        image_bgr,
        segments,
        line_annotations,
        lengths,
        labels,
        pdf_notes or {},
    )
