import csv
import json
from pathlib import Path

from app.processing.dimension_parser import ParsedDimension
from app.processing.segment_builder import SegmentModel


def export_segments_json(
    path: Path,
    segments: list[SegmentModel],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
) -> None:
    rows = []
    for seg in segments:
        dim, conf = labels.get(seg.segment_id, (None, seg.confidence))
        length_ft, mode = lengths.get(seg.segment_id, (None, ""))
        row = {
            "segmentId": seg.segment_id,
            "pageNumber": seg.page_number,
            "type": seg.segment_type,
            "shape": seg.shape,
            "sizeText": dim.raw if dim else None,
            "widthIn": dim.width_in if dim else None,
            "heightIn": dim.height_in if dim else None,
            "diameterIn": dim.diameter_in if dim else None,
            "lengthFt": length_ft,
            "measurementMode": mode,
            "confidence": conf,
            "bbox": list(seg.bbox),
            "polyline": [[p[0], p[1]] for p in seg.polyline],
        }
        rows.append(row)
    path.write_text(json.dumps({"segments": rows}, indent=2))


def export_segments_csv(
    path: Path,
    segments: list[SegmentModel],
    labels: dict[str, tuple[ParsedDimension | None, float]],
    lengths: dict[str, tuple[float | None, str]],
) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "segmentId",
                "pageNumber",
                "type",
                "shape",
                "sizeText",
                "lengthFt",
                "confidence",
                "bbox_x0",
                "bbox_y0",
                "bbox_x1",
                "bbox_y1",
            ]
        )
        for seg in segments:
            dim, conf = labels.get(seg.segment_id, (None, seg.confidence))
            length_ft, _ = lengths.get(seg.segment_id, (None, ""))
            x0, y0, x1, y1 = seg.bbox
            w.writerow(
                [
                    seg.segment_id,
                    seg.page_number,
                    seg.segment_type,
                    seg.shape,
                    dim.raw if dim else "",
                    length_ft if length_ft is not None else "",
                    f"{conf:.3f}",
                    x0,
                    y0,
                    x1,
                    y1,
                ]
            )
