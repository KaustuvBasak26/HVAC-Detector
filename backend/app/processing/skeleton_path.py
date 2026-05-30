"""Morphological skeleton and geodesic centerline polylines for duct masks."""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np


def morphological_skeleton(binary: np.ndarray) -> np.ndarray:
    """
    Lantuéjoul morphological skeleton (OpenCV). Input uint8 0/255 foreground 255.
    """
    img = ((binary > 0).astype(np.uint8)) * 255
    if cv2.countNonZero(img) == 0:
        return np.zeros_like(binary, dtype=np.uint8)
    skel = np.zeros_like(img)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    it = 0
    while True:
        opened = cv2.morphologyEx(img, cv2.MORPH_OPEN, element)
        temp = cv2.subtract(img, opened)
        skel = cv2.bitwise_or(skel, temp)
        img = cv2.erode(img, element)
        it += 1
        if cv2.countNonZero(img) == 0 or it > 2048:
            break
    return skel


def _neighbor_count(skel: np.ndarray, y: int, x: int) -> int:
    patch = (skel[y - 1 : y + 2, x - 1 : x + 2] > 0).astype(np.uint8)
    return int(patch.sum()) - (1 if skel[y, x] > 0 else 0)


def _largest_skeleton_cc(skel: np.ndarray) -> np.ndarray:
    bin8 = (skel > 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bin8, connectivity=8)
    if n <= 1:
        return skel
    best = 1
    best_a = stats[1, cv2.CC_STAT_AREA]
    for i in range(2, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a > best_a:
            best_a = a
            best = i
    out = np.zeros_like(skel)
    out[labels == best] = 255
    return out


def _bfs_farthest_path(skel: np.ndarray) -> list[tuple[float, float]] | None:
    skel = _largest_skeleton_cc(skel)
    ys, xs = np.where(skel > 0)
    if len(ys) < 3:
        return None
    h, w = skel.shape
    endpoints: list[tuple[int, int]] = []
    for y, x in zip(ys, xs, strict=True):
        if _neighbor_count(skel, y, x) <= 1:
            endpoints.append((y, x))
    if not endpoints:
        start = (int(ys[0]), int(xs[0]))
    else:
        start = endpoints[0]

    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    dist: dict[tuple[int, int], int] = {start: 0}
    q: deque[tuple[int, int]] = deque([start])
    far = start
    while q:
        cy, cx = q.popleft()
        d0 = dist[(cy, cx)]
        if d0 > dist.get(far, -1):
            far = (cy, cx)
        for dy, dx in (
            (-1, -1),
            (-1, 0),
            (-1, 1),
            (0, -1),
            (0, 1),
            (1, -1),
            (1, 0),
            (1, 1),
        ):
            ny, nx = cy + dy, cx + dx
            if ny < 0 or nx < 0 or ny >= h or nx >= w:
                continue
            if skel[ny, nx] == 0:
                continue
            if (ny, nx) in parent:
                continue
            parent[(ny, nx)] = (cy, cx)
            dist[(ny, nx)] = d0 + 1
            q.append((ny, nx))

    if far == start and len(parent) < 3:
        return None

    path_rev: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = far
    while cur is not None:
        path_rev.append(cur)
        cur = parent[cur]
    path = path_rev[::-1]
    if len(path) < 2:
        return None
    max_pts = 280
    step = max(1, len(path) // max_pts) if len(path) > max_pts else 1
    slim = path[::step]
    if slim[-1] != path[-1]:
        slim.append(path[-1])
    return [(float(x), float(y)) for y, x in slim]


def skeleton_polyline_from_contour(
    cnt: np.ndarray, max_roi: int = 900
) -> list[tuple[float, float]] | None:
    """
    Pixel chain along the medial axis of a filled contour. Coordinates are in the same
    space as the input contour (plan ROI).
    """
    x, y, bw, bh = cv2.boundingRect(cnt)
    if bw < 3 or bh < 3:
        return None

    scale = 1.0
    rw, rh = bw, bh
    if max(bw, bh) > max_roi:
        scale = max_roi / float(max(bw, bh))
        rw = max(3, int(bw * scale))
        rh = max(3, int(bh * scale))

    pad = 2
    roi = np.zeros((rh + pad * 2, rw + pad * 2), dtype=np.uint8)
    pts = np.asarray(cnt, dtype=np.float32).reshape(-1, 2)
    inner = np.empty_like(pts)
    inner[:, 0] = (pts[:, 0] - float(x)) * scale + pad
    inner[:, 1] = (pts[:, 1] - float(y)) * scale + pad
    cnt_adj = np.round(inner).astype(np.int32).reshape(-1, 1, 2)
    cnt_adj[:, 0, 0] = np.clip(cnt_adj[:, 0, 0], 0, rw + pad * 2 - 1)
    cnt_adj[:, 0, 1] = np.clip(cnt_adj[:, 0, 1], 0, rh + pad * 2 - 1)
    cv2.drawContours(roi, [cnt_adj], -1, 255, thickness=-1)
    sk = morphological_skeleton(roi)
    path = _bfs_farthest_path(sk)
    if path is None or len(path) < 2:
        return None
    inv = 1.0 / scale if scale != 1.0 else 1.0
    out: list[tuple[float, float]] = []
    for px, py in path:
        gx = (px - pad) * inv + x
        gy = (py - pad) * inv + y
        out.append((float(gx), float(gy)))
    return out
