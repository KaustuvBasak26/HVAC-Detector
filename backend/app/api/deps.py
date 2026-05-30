from __future__ import annotations

from fastapi import Header

from app.core.viewer_token import verify_viewer_token


def require_job_viewer(
    job_id: str,
    x_job_viewer_token: str | None = Header(default=None, alias="X-Job-Viewer-Token"),
) -> None:
    verify_viewer_token(job_id, x_job_viewer_token)
