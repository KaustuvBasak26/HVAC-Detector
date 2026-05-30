from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings


def assert_secure_job_output(job_id: str, storage_key: str) -> Path:
    """Resolve a job output file and reject paths outside that job's output tree."""
    prefix = f"jobs/{job_id}/"
    if not storage_key.startswith(prefix):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
    path = (settings.data_dir / storage_key).resolve()
    allowed_root = (settings.data_dir / "jobs" / job_id).resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError:
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"}) from None
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
