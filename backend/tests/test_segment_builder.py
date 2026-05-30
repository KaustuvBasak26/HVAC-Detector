from __future__ import annotations

import numpy as np

from app.processing.segment_builder import contour_centerline_and_bbox


def test_contour_centerline_horizontal_bar():
    cnt = np.array([[[0, 0]], [[100, 0]], [[100, 20]], [[0, 20]]], dtype=np.int32)
    poly, bbox = contour_centerline_and_bbox(cnt)
    x0, y0, x1, y1 = bbox
    assert x0 == 0 and y0 == 0
    assert x1 > x0 and y1 > y0
    assert len(poly) == 2
    assert poly[0][1] == poly[1][1]
