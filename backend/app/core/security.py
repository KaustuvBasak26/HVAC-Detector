from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings


def resolve_data_file(relative_path: str) -> Path:
    """Resolve a path under the data directory and reject traversal escapes."""
    if not relative_path or relative_path.startswith("/"):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
    if "/../" in relative_path or relative_path.startswith("../"):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
    root = settings.data_dir.resolve()
    path = (settings.data_dir / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"}) from None
    return path


def assert_job_output_path(job_id: str, storage_key: str) -> Path:
    """Resolve a job output file and reject paths outside that job's output tree."""
    prefix = f"jobs/{job_id}/outputs/"
    if not storage_key.startswith(prefix):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
    path = resolve_data_file(storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    return path


def secure_response_headers(*, inline: bool = False) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline" if inline else "attachment",
    }
    return headers
