import gc
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.demo_cleanup import delete_uploaded_pdf, purge_demo_storage
from app.models.db_models import DuctSegment, FileRecord, Job, JobOutput, User
from app.processing.dimension_parser import ParsedDimension
from app.processing.pipeline import PagePipelineResult, run_pipeline_on_pdf, write_pipeline_outputs
from app.processing.segment_builder import SegmentModel, dumps_polyline


def ensure_local_user(db: Session) -> str:
    u = db.query(User).filter(User.email == "local@localhost").first()
    if u:
        return u.id
    u = User(email="local@localhost", name="Local User", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u.id


def process_job_sync(
    db: Session,
    job_id: str,
    page_selection_mode: str = "all",
    page_numbers: list[int] | None = None,
    output_formats: list[str] | None = None,
) -> None:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return
    file_rec = db.query(FileRecord).filter(FileRecord.id == job.file_id).first()
    if not file_rec:
        _fail(db, job, "invalid_pdf", "File record missing")
        return

    pdf_path = settings.data_dir / file_rec.storage_key
    if not pdf_path.is_file():
        _fail(db, job, "invalid_pdf", "PDF not found on disk")
        return

    job.status = "processing"
    job.progress_percent = 2
    job.current_step = "Starting"
    job.updated_at = datetime.utcnow()
    db.commit()

    out_fmt = list(output_formats or ["png", "pdf", "json", "csv"])
    if settings.low_memory_mode:
        out_fmt = [fmt for fmt in out_fmt if fmt in {"png", "json"}]
    if "png" not in out_fmt:
        out_fmt.insert(0, "png")

    def _report_progress(pct: int, step: str) -> None:
        job.progress_percent = min(100, max(0, int(pct)))
        job.current_step = step
        job.updated_at = datetime.utcnow()
        db.commit()

    try:
        results = run_pipeline_on_pdf(
            pdf_path,
            page_selection_mode=page_selection_mode or "all",
            page_numbers=page_numbers or [],
            output_formats=out_fmt,
            on_progress=_report_progress,
        )
    except ValueError as e:
        code = str(e) if str(e) in ("invalid_pdf",) else "unexpected_internal_error"
        _fail(db, job, code, str(e))
        if file_rec:
            delete_uploaded_pdf(file_rec.storage_key)
        return
    except Exception as e:
        _fail(db, job, "duct_detection_failed", str(e))
        if file_rec:
            delete_uploaded_pdf(file_rec.storage_key)
        return

    job.progress_percent = 85
    job.current_step = "export"
    job.updated_at = datetime.utcnow()
    db.commit()

    job_dir = settings.data_dir / "jobs" / job_id
    artifact_keys = write_pipeline_outputs(results, job_dir, job_id, out_fmt)

    db.query(DuctSegment).filter(DuctSegment.job_id == job_id).delete()
    db.query(JobOutput).filter(JobOutput.job_id == job_id).delete()

    all_segments: list[SegmentModel] = []
    all_labels: dict[str, tuple[ParsedDimension | None, float]] = {}
    all_lengths: dict[str, tuple[float | None, str]] = {}
    for r in results:
        all_segments.extend(r.segments)
        all_labels.update(r.labels)
        all_lengths.update(r.lengths)

    for seg in all_segments:
        dim, conf = all_labels.get(seg.segment_id, (None, seg.confidence))
        length_ft, _ = all_lengths.get(seg.segment_id, (None, ""))
        db.add(
            DuctSegment(
                job_id=job_id,
                page_number=seg.page_number,
                segment_code=seg.segment_id,
                segment_type=seg.segment_type,
                shape=seg.shape,
                size_text=dim.raw if dim else None,
                width_value=dim.width_in if dim else None,
                height_value=dim.height_in if dim else None,
                diameter_value=dim.diameter_in if dim else None,
                length_value=length_ft,
                length_unit="ft",
                confidence_score=conf,
                bbox_json=json.dumps(list(seg.bbox)),
                polyline_json=dumps_polyline(seg.polyline),
            )
        )

    mime = {
        "annotated_png": "image/png",
        "annotated_pdf": "application/pdf",
        "segments_json": "application/json",
        "segments_csv": "text/csv",
    }
    for kind, key in artifact_keys.items():
        db.add(
            JobOutput(
                job_id=job_id,
                output_type=kind,
                storage_key=key,
                mime_type=mime.get(kind, "application/octet-stream"),
            )
        )

    job.status = "completed"
    job.progress_percent = 100
    job.current_step = None
    job.completed_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    db.commit()
    delete_uploaded_pdf(file_rec.storage_key)
    del results, all_segments, all_labels, all_lengths, artifact_keys
    gc.collect()


def _fail(db: Session, job: Job, code: str, message: str) -> None:
    job.status = "failed"
    job.error_code = code
    job.error_message = message
    job.updated_at = datetime.utcnow()
    db.commit()
