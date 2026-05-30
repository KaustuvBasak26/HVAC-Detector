from __future__ import annotations

import gc
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.db_models import DuctSegment, FileRecord, Job, JobOutput


def purge_demo_storage(db: Session) -> None:
    """Drop all prior uploads, artifacts, and job rows (demo / Render Free)."""
    if not settings.demo_mode:
        return
    data = settings.data_dir
    for sub in ("inputs", "jobs"):
        folder = data / sub
        if folder.is_dir():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
    db.query(DuctSegment).delete(synchronize_session=False)
    db.query(JobOutput).delete(synchronize_session=False)
    db.query(Job).delete(synchronize_session=False)
    db.query(FileRecord).delete(synchronize_session=False)
    db.commit()
    gc.collect()


def delete_uploaded_pdf(storage_key: str) -> None:
    if not settings.demo_mode:
        return
    path = settings.data_dir / storage_key
    if path.is_file():
        path.unlink(missing_ok=True)
    parent = path.parent
    if parent.is_dir() and not any(parent.iterdir()):
        shutil.rmtree(parent, ignore_errors=True)
    gc.collect()


def release_job_storage(db: Session, job_id: str) -> bool:
    """Remove on-disk artifacts and DB rows for a finished demo job."""
    if not settings.demo_mode:
        return False
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return False
    file_rec = db.query(FileRecord).filter(FileRecord.id == job.file_id).first()
    job_dir = settings.data_dir / "jobs" / job_id
    if job_dir.is_dir():
        shutil.rmtree(job_dir, ignore_errors=True)
    if file_rec:
        delete_uploaded_pdf(file_rec.storage_key)
        db.delete(file_rec)
    db.query(DuctSegment).filter(DuctSegment.job_id == job_id).delete(synchronize_session=False)
    db.query(JobOutput).filter(JobOutput.job_id == job_id).delete(synchronize_session=False)
    db.delete(job)
    db.commit()
    gc.collect()
    return True
