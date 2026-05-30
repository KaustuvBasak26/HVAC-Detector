import math
import re

import cv2
import numpy as np

from app.core.config import settings
from app.processing.dimension_parser import ParsedDimension
from app.processing.measurement_engine import polyline_length_px
from app.processing.segment_builder import SegmentModel


def _stroke_thickness_capped(path_len_px: float, requested: int) -> int:
    """Very thick strokes on short paths look like dots; cap width vs path length."""
    if path_len_px < 12.0:
        return 0
    return max(5, min(requested, int(path_len_px * 0.42)))


def _centerline_thickness(path_len_px: float, cap: int) -> int:
    """Bold markup strokes (Sample annotation.png style — strong blue duct runs)."""
    if path_len_px < 5.0:
        return 0
    return max(6, min(cap, int(6.0 + path_len_px * 0.056)))


def _draw_polyline_path(
    img: np.ndarray,
    poly: list[tuple[float, float]],
    color: tuple[int, int, int],
    thick: int,
) -> None:
    """Single continuous polyline (OpenCV polylines) clipped to the image."""
    if thick <= 0 or len(poly) < 2:
        return
    h, w = img.shape[:2]
    pts: list[list[int]] = []
    for p in poly:
        if not all(math.isfinite(float(v)) for v in p):
            continue
        xi = int(round(max(0.0, min(float(w - 1), float(p[0])))))
        yi = int(round(max(0.0, min(float(h - 1), float(p[1])))))
        if pts and pts[-1][0] == xi and pts[-1][1] == yi:
            continue
        pts.append([xi, yi])
    if len(pts) < 2:
        return
    arr = np.asarray(pts, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(img, [arr], isClosed=False, color=color, thickness=thick, lineType=cv2.LINE_8)


def _blend_polyline_stroke_float(
    canvas: np.ndarray,
    poly: list[tuple[float, float]],
    color_bgr: np.ndarray,
    alpha: float,
    thick: int,
    h: int,
    w: int,
) -> None:
    """Alpha-blend one antialiased polyline stroke onto float32 BGR ``canvas``."""
    if thick <= 0 or len(poly) < 2:
        return
    pts: list[list[int]] = []
    for p in poly:
        if not all(math.isfinite(float(v)) for v in p):
            continue
        xi = int(round(max(0.0, min(float(w - 1), float(p[0])))))
        yi = int(round(max(0.0, min(float(h - 1), float(p[1])))))
        if pts and pts[-1][0] == xi and pts[-1][1] == yi:
            continue
        pts.append([xi, yi])
    if len(pts) < 2:
        return
    mask = np.zeros((h, w), dtype=np.uint8)
    arr = np.asarray(pts, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(mask, [arr], isClosed=False, color=255, thickness=thick, lineType=cv2.LINE_AA)
    m = mask > 0
    a = float(max(0.0, min(1.0, alpha)))
    canvas[m] = canvas[m] * (1.0 - a) + color_bgr * a


def _polyline_midpoint(poly: list[tuple[float, float]]) -> tuple[float, float]:
    """Geometric midpoint along the chain (for label placement on the duct path)."""
    if not poly:
        return 0.0, 0.0
    if len(poly) < 2:
        return float(poly[0][0]), float(poly[0][1])
    segs: list[float] = []
    total = 0.0
    for i in range(len(poly) - 1):
        a, b = poly[i], poly[i + 1]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append(d)
        total += d
    if total < 1e-6:
        return float(poly[len(poly) // 2][0]), float(poly[len(poly) // 2][1])
    target = total * 0.5
    acc = 0.0
    idx = 0
    for i, d in enumerate(segs):
        if acc + d >= target:
            idx = i
            break
        acc += d
    t = (target - acc) / max(segs[idx], 1e-6)
    a, b = poly[idx], poly[idx + 1]
    return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])


def _is_return(seg: SegmentModel) -> bool:
    return seg.segment_type == "return"


def _segment_id_sort_key(segment_id: str) -> tuple[int, str]:
    m = re.match(r"^D-(\d+)$", segment_id.strip(), re.I)
    if m:
        return (int(m.group(1)), segment_id)
    return (10**9, segment_id)


def _format_length_cell(length_ft: float | None) -> str:
    if length_ft is None:
        return "—"
    s = f"{float(length_ft):.2f}"
    s = s.rstrip("0").rstrip(".")
    return f"{s} ft"


def _draw_legend_panel(
    out: np.ndarray,
    segments: list[SegmentModel],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
    w: int,
    h: int,
    diag: float,
) -> None:
    """
    Bottom-left tabular legend: ID, size callout, measured length, system.
    Keeps the floor plan readable; details live here instead of on the ducts.
    """
    if not segments:
        return
    margin = max(14, int(diag * 0.007))
    panel_w = min(int(w * 0.46), 760)
    row_fs = max(0.36, min(0.66, diag / 2600.0))
    title_fs = max(0.48, min(0.82, diag / 2100.0))
    th_row = max(1, int(round(row_fs * 1.35)))
    th_title = max(2, int(round(title_fs * 1.45)))
    row_gap = max(5, int(6 + row_fs * 4))

    ordered = sorted(segments, key=lambda s: _segment_id_sort_key(s.segment_id))

    def row_h_sample() -> int:
        (_, rh), _ = cv2.getTextSize("Hg", cv2.FONT_HERSHEY_SIMPLEX, row_fs, th_row)
        return int(rh + row_gap)

    rh = row_h_sample()
    (_, title_h), _ = cv2.getTextSize("DUCT SCHEDULE (detected)", cv2.FONT_HERSHEY_DUPLEX, title_fs, th_title)
    header_label = "ID          Size             Length       System"
    (_, header_h), _ = cv2.getTextSize(header_label, cv2.FONT_HERSHEY_SIMPLEX, row_fs * 0.95, th_row)
    title_block = int(title_h + header_h + margin * 2 + 10)
    max_panel_h = int(h * 0.31)
    avail = max_panel_h - title_block - margin - rh
    max_rows = max(4, min(len(ordered), max(1, avail // max(rh, 1))))
    truncated = len(ordered) > max_rows
    visible = ordered[:max_rows]

    footer_h = int(rh * 1.1) if truncated else 0
    panel_h = title_block + max_rows * rh + footer_h + margin

    x0 = margin
    y1 = h - margin
    y0 = max(margin + 40, y1 - panel_h)
    x1 = min(w - margin, x0 + panel_w)

    cv2.rectangle(out, (x0, y0), (x1, y1), (248, 249, 252), -1)
    cv2.rectangle(out, (x0, y0), (x1, y1), (88, 92, 102), 1)

    tx = x0 + margin // 2 + 4
    (_, th_t), bl_t = cv2.getTextSize(
        "DUCT SCHEDULE (detected)", cv2.FONT_HERSHEY_DUPLEX, title_fs, th_title
    )
    yb = y0 + margin + th_t + max(0, bl_t - 2)
    cv2.putText(
        out,
        "DUCT SCHEDULE (detected)",
        (tx, yb),
        cv2.FONT_HERSHEY_DUPLEX,
        title_fs,
        (32, 36, 48),
        th_title,
        cv2.LINE_AA,
    )
    y_sep = yb + bl_t + 10
    cv2.line(out, (tx, y_sep), (x1 - margin // 2, y_sep), (160, 165, 175), 1, cv2.LINE_AA)
    (_, hh), bl_h = cv2.getTextSize(
        header_label, cv2.FONT_HERSHEY_SIMPLEX, row_fs * 0.92, th_row
    )
    yb = y_sep + hh + 8
    cv2.putText(
        out,
        header_label,
        (tx, yb),
        cv2.FONT_HERSHEY_SIMPLEX,
        row_fs * 0.92,
        (55, 60, 72),
        th_row,
        cv2.LINE_AA,
    )
    yb += int(max(rh, hh + bl_h) + 4)

    col_id = tx
    col_sz = tx + int(panel_w * 0.16)
    col_len = tx + int(panel_w * 0.42)
    col_sys = tx + int(panel_w * 0.68)

    dim_gray = (78, 82, 92)
    for seg in visible:
        dim_conf = labels.get(seg.segment_id, (None, seg.confidence))
        dim, conf = dim_conf[0], dim_conf[1]
        length_ft, _note = lengths.get(seg.segment_id, (None, ""))
        size_cell = (dim.raw[:18] + "…") if dim and len(dim.raw) > 18 else (dim.raw if dim else "—")
        len_cell = _format_length_cell(length_ft)
        sys_cell = "Return" if _is_return(seg) else "Supply"
        col = dim_gray if conf >= 0.5 else (110, 112, 120)

        cv2.putText(
            out,
            seg.segment_id[:14],
            (col_id, yb),
            cv2.FONT_HERSHEY_SIMPLEX,
            row_fs,
            col,
            th_row,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            size_cell,
            (col_sz, yb),
            cv2.FONT_HERSHEY_SIMPLEX,
            row_fs,
            col,
            th_row,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            len_cell,
            (col_len, yb),
            cv2.FONT_HERSHEY_SIMPLEX,
            row_fs,
            col,
            th_row,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            sys_cell,
            (col_sys, yb),
            cv2.FONT_HERSHEY_SIMPLEX,
            row_fs,
            col,
            th_row,
            cv2.LINE_AA,
        )
        yb += rh

    if truncated:
        msg = f"+ {len(ordered) - max_rows} more (see JSON / CSV export)"
        cv2.putText(
            out,
            msg[:56],
            (col_id, min(y1 - margin // 2, yb + 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            row_fs * 0.88,
            (95, 98, 108),
            th_row,
            cv2.LINE_AA,
        )


def _draw_metadata(
    out: np.ndarray,
    segments: list[SegmentModel],
    contours: list[np.ndarray],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
    w: int,
    h: int,
    layout: str,
    font_scale: float,
    font_thick: int,
    diag: float,
) -> None:
    lo = (layout or "legend").strip().lower()
    if lo in ("none", "off", "false"):
        return
    if lo in ("on_plan", "onplan", "boxes", "inline"):
        _draw_segment_label_boxes(
            out, segments, contours, labels, lengths, w, h, font_scale, font_thick
        )
        return
    _draw_legend_panel(out, segments, labels, lengths, w, h, diag)


def _draw_segment_label_boxes(
    out: np.ndarray,
    segments: list[SegmentModel],
    contours: list[np.ndarray],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
    w: int,
    h: int,
    font_scale: float,
    font_thick: int,
) -> None:
    for seg, _cnt in zip(segments, contours, strict=True):
        dim_conf = labels.get(seg.segment_id, (None, seg.confidence))
        length_ft, _ = lengths.get(seg.segment_id, (None, ""))
        dim = dim_conf[0]
        line1 = dim.raw if dim else seg.segment_id
        bits = [seg.segment_id]
        if length_ft is not None:
            bits.append(f"{length_ft} ft")
        line2 = " · ".join(bits)

        fs1 = font_scale * 1.08
        fs2 = font_scale * 0.82
        th1 = max(2, font_thick)
        th2 = max(1, font_thick - 1)
        (tw1, th1h), _ = cv2.getTextSize(line1[:48], cv2.FONT_HERSHEY_DUPLEX, fs1, th1)
        (tw2, th2h), _ = cv2.getTextSize(line2[:64], cv2.FONT_HERSHEY_SIMPLEX, fs2, th2)
        tw = max(tw1, tw2)
        th_box = th1h + th2h + int(14 + font_scale * 6)

        mx, my = _polyline_midpoint(seg.polyline)
        tx = int(mx - tw * 0.5 - 6)
        ty = int(my - th_box * 0.5)
        tx = max(4, min(tx, w - tw - 16))
        ty = max(th_box + 4, min(ty, h - 8))

        pad = int(6 + font_scale * 2)
        x0, y0 = tx - pad, ty - th_box
        x1, y1 = tx + tw + pad * 2, ty + pad
        x1 = min(w - 2, x1)

        is_ret = _is_return(seg)
        if is_ret:
            fill = (240, 248, 255) if dim else (255, 248, 242)
            border = (50, 110, 220)
            col_dim = (25, 70, 200)
            col_sub = (45, 95, 180)
        else:
            fill = (255, 248, 225) if dim else (245, 250, 255)
            border = (120, 55, 25)
            col_dim = (95, 35, 15)
            col_sub = (70, 55, 45)
        cv2.rectangle(out, (x0, y0), (x1, y1), fill, -1)
        cv2.rectangle(out, (x0, y0), (x1, y1), border, max(2, th1 - 1))
        y_line1 = y0 + th1h + pad // 2
        cv2.putText(
            out,
            line1[:48],
            (tx, y_line1),
            cv2.FONT_HERSHEY_DUPLEX,
            fs1,
            col_dim,
            th1,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            line2[:64],
            (tx, y_line1 + th2h + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            fs2,
            col_sub,
            th2,
            cv2.LINE_AA,
        )


def _render_markup_style(
    base_bgr: np.ndarray,
    segments: list[SegmentModel],
    contours: list[np.ndarray],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
    fill_alpha: float = 0.52,
    low_conf_threshold: float = 0.5,
    metadata_layout: str = "legend",
) -> np.ndarray:
    """
    Legacy “markup” look: saturated translucent contour wash + very thick opaque path stacks.
    """
    supply_fill = np.array([255, 135, 55], dtype=np.float32)
    return_fill = np.array([55, 150, 255], dtype=np.float32)
    low_supply = np.array([235, 125, 65], dtype=np.float32)
    low_return = np.array([75, 135, 235], dtype=np.float32)

    result = base_bgr.astype(np.float32)
    h, w = base_bgr.shape[:2]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    for seg, cnt in zip(segments, contours, strict=True):
        dim_conf = labels.get(seg.segment_id, (None, seg.confidence))
        _, conf = dim_conf
        is_ret = _is_return(seg)
        color_f = return_fill if is_ret else supply_fill
        alpha = fill_alpha
        if conf < low_conf_threshold:
            color_f = low_return if is_ret else low_supply
            alpha = fill_alpha * 0.62
        if seg.shape == "diffuser":
            alpha = fill_alpha * 0.48
            color_f = return_fill * 0.92 if is_ret else supply_fill * 0.92

        cnt_i = np.asarray(cnt, dtype=np.int32).reshape(-1, 1, 2)
        if cnt_i.size >= 6:
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [cnt_i], -1, 255, thickness=-1)
            mask = cv2.dilate(mask, kernel, iterations=2)
            m = mask > 0
            result[m] = result[m] * (1.0 - alpha) + color_f * alpha

    out = np.clip(result, 0, 255).astype(np.uint8)

    diag = float((w * w + h * h) ** 0.5)
    font_scale = max(0.62, min(1.55, diag / 1850.0))
    font_thick = max(2, int(round(font_scale * 1.1)))
    core_thick = max(14, min(42, int(round(diag * 0.0065))))
    mid_thick = core_thick + max(6, core_thick // 3)
    halo_thick = mid_thick + max(10, core_thick // 2)

    stroke_specs: list[
        tuple[
            list[tuple[float, float]],
            tuple[int, int, int],
            tuple[int, int, int],
            tuple[int, int, int],
            int,
        ]
    ] = []

    for seg, cnt in zip(segments, contours, strict=True):
        dim_conf = labels.get(seg.segment_id, (None, seg.confidence))
        _, conf = dim_conf
        is_ret = _is_return(seg)
        if seg.shape == "diffuser":
            edge = (190, 90, 190) if not is_ret else (200, 120, 200)
        elif seg.shape == "flex":
            edge = (175, 95, 45) if not is_ret else (70, 165, 255)
        else:
            edge = (200, 100, 50) if not is_ret else (65, 170, 255)
        if conf < low_conf_threshold:
            edge = (150, 85, 55) if not is_ret else (85, 145, 220)

        cnt_i = np.asarray(cnt, dtype=np.int32).reshape(-1, 1, 2)
        if cnt_i.size >= 6:
            cv2.drawContours(out, [cnt_i], -1, edge, thickness=max(4, core_thick // 4))

        if seg.shape == "diffuser":
            if not is_ret:
                core, mid, halo = (220, 40, 220), (255, 120, 255), (255, 255, 255)
            else:
                core, mid, halo = (200, 60, 200), (240, 140, 240), (255, 250, 255)
        elif seg.shape == "flex":
            if not is_ret:
                core, mid, halo = (255, 40, 0), (255, 140, 60), (255, 255, 255)
            else:
                core, mid, halo = (0, 90, 255), (80, 180, 255), (255, 255, 255)
        elif not is_ret:
            core, mid, halo = (255, 50, 0), (255, 160, 70), (255, 255, 255)
        else:
            core, mid, halo = (0, 100, 255), (120, 200, 255), (255, 255, 255)
        if conf < low_conf_threshold:
            if not is_ret:
                core, mid, halo = (200, 70, 30), (230, 150, 90), (248, 248, 248)
            else:
                core, mid, halo = (40, 130, 230), (140, 200, 255), (248, 248, 248)

        poly = seg.polyline
        plen = polyline_length_px(poly)
        th_h = _stroke_thickness_capped(plen, halo_thick)
        th_m = _stroke_thickness_capped(plen, mid_thick)
        th_c = _stroke_thickness_capped(plen, core_thick)
        stroke_specs.append((poly, halo, mid, core, th_c))
        _draw_polyline_path(out, poly, halo, th_h)
        _draw_polyline_path(out, poly, mid, th_m)
        _draw_polyline_path(out, poly, core, th_c)

    _draw_metadata(
        out, segments, contours, labels, lengths, w, h, metadata_layout, font_scale, font_thick, diag
    )

    for poly, _halo, _mid, core, th_c in stroke_specs:
        _draw_polyline_path(out, poly, core, max(6, th_c - 2))

    return out


def _render_centerline_style(
    base_bgr: np.ndarray,
    segments: list[SegmentModel],
    contours: list[np.ndarray],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
    low_conf_threshold: float,
    centerline_alpha: float,
    width_scale: float,
    contour_hint_alpha: float,
    metadata_layout: str,
    mono_blue: bool,
) -> np.ndarray:
    """
    Reference-style overlay: thick translucent strokes on polylines (no solid contour slabs).
    """
    h, w = base_bgr.shape[:2]
    canvas = base_bgr.astype(np.float32)
    diag = float((w * w + h * h) ** 0.5)
    base_thick = max(9, min(32, int(round(diag * width_scale))))
    font_scale = max(0.62, min(1.55, diag / 1850.0))
    font_thick = max(2, int(round(font_scale * 1.1)))

    # Optional whisper of contour so short / noisy segments still read a little
    if contour_hint_alpha > 1e-6:
        hint_col_s = np.array([240, 120, 55], dtype=np.float32)
        hint_col_r = np.array([170, 130, 95], dtype=np.float32)
        for seg, cnt in zip(segments, contours, strict=True):
            dim_conf = labels.get(seg.segment_id, (None, seg.confidence))
            _, conf = dim_conf
            is_ret = _is_return(seg)
            color_f = hint_col_s if mono_blue or not is_ret else hint_col_r
            a = contour_hint_alpha * (0.65 if conf < low_conf_threshold else 1.0)
            cnt_i = np.asarray(cnt, dtype=np.int32).reshape(-1, 1, 2)
            if cnt_i.size < 6:
                continue
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [cnt_i], -1, 255, thickness=-1)
            m = mask > 0
            canvas[m] = canvas[m] * (1.0 - a) + color_f * a

    white = np.array([255.0, 255.0, 255.0], dtype=np.float32)
    for seg, _cnt in zip(segments, contours, strict=True):
        dim_conf = labels.get(seg.segment_id, (None, seg.confidence))
        _, conf = dim_conf
        is_ret = _is_return(seg)
        poly = seg.polyline
        plen = polyline_length_px(poly)
        th = _centerline_thickness(plen, base_thick)
        if th <= 0:
            continue
        a = centerline_alpha * (0.72 if conf < low_conf_threshold else 1.0)
        duct_blue = np.array(
            [
                float(settings.annotation_duct_blue_b),
                float(settings.annotation_duct_blue_g),
                float(settings.annotation_duct_blue_r),
            ],
            dtype=np.float32,
        )
        if seg.shape == "diffuser":
            if mono_blue:
                main = duct_blue * np.array([0.92, 0.95, 1.02], dtype=np.float32)
            else:
                main = (
                    np.array([235, 85, 200], dtype=np.float32)
                    if not is_ret
                    else np.array([220, 110, 215], dtype=np.float32)
                )
        elif seg.shape == "flex":
            if mono_blue:
                main = duct_blue
            else:
                main = (
                    np.array([230, 95, 55], dtype=np.float32)
                    if not is_ret
                    else np.array([185, 150, 100], dtype=np.float32)
                )
        elif mono_blue or not is_ret:
            main = duct_blue
        else:
            # Softer slate / teal when mono_blue is off
            main = np.array([195, 150, 105], dtype=np.float32)

        halo_w = th + max(1, int(round(th * 0.28)))
        _blend_polyline_stroke_float(canvas, poly, white, min(0.12, a * 0.22), halo_w, h, w)
        _blend_polyline_stroke_float(canvas, poly, main, a, th, h, w)

    out = np.clip(canvas, 0, 255).astype(np.uint8)
    _draw_metadata(
        out, segments, contours, labels, lengths, w, h, metadata_layout, font_scale, font_thick, diag
    )
    return out


def render_annotations(
    base_bgr: np.ndarray,
    segments: list[SegmentModel],
    contours: list[np.ndarray],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
    fill_alpha: float = 0.52,
    low_conf_threshold: float = 0.5,
    style: str = "centerline",
    centerline_alpha: float = 0.5,
    centerline_width_scale: float = 0.00135,
    centerline_contour_hint_alpha: float = 0.0,
    metadata_layout: str = "legend",
    mono_blue: bool = True,
) -> np.ndarray:
    """
    ``centerline`` (default): translucent blue/teal strokes like clean CAD markup sheets.
    ``markup``: previous heavy filled contours + thick opaque path stacks.
    """
    if style == "markup":
        return _render_markup_style(
            base_bgr,
            segments,
            contours,
            labels,
            lengths,
            fill_alpha=fill_alpha,
            low_conf_threshold=low_conf_threshold,
            metadata_layout=metadata_layout,
        )
    return _render_centerline_style(
        base_bgr,
        segments,
        contours,
        labels,
        lengths,
        low_conf_threshold=low_conf_threshold,
        centerline_alpha=centerline_alpha,
        width_scale=centerline_width_scale,
        contour_hint_alpha=centerline_contour_hint_alpha,
        metadata_layout=metadata_layout,
        mono_blue=mono_blue,
    )
