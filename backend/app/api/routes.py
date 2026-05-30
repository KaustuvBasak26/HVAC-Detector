import json
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import DuctSegment, FileRecord, Job, JobOutput
from app.schemas.api import (
    JobCreateRequest,
    JobCreateResponse,
    JobResultResponse,
    JobStatusResponse,
    ResultSummary,
    SegmentItem,
    SegmentsListResponse,
    UploadResponse,
)
from app.workers.job_processor import ensure_local_user, process_job_sync

router = APIRouter()


def _run_job_background(
    job_id: str,
    page_selection_mode: str,
    page_numbers: list[int],
    output_formats: list[str],
) -> None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        process_job_sync(db, job_id, page_selection_mode, page_numbers, output_formats)
    finally:
        db.close()


@router.post("/api/files/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_FILE_TYPE", "message": "Only PDF files are supported."},
        )
    user_id = ensure_local_user(db)
    raw = await file.read()
    max_b = settings.max_upload_size_mb * 1024 * 1024
    if len(raw) > max_b:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": "File exceeds upload limit."},
        )
    file_id = str(uuid.uuid4())
    sub = settings.data_dir / "inputs" / file_id
    sub.mkdir(parents=True, exist_ok=True)
    dest = sub / "original.pdf"
    dest.write_bytes(raw)

    import fitz

    try:
        doc = fitz.open(dest)
        n = doc.page_count
        doc.close()
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PDF", "message": "Could not read PDF."},
        )

    key = f"inputs/{file_id}/original.pdf"
    rec = FileRecord(
        id=file_id,
        user_id=user_id,
        original_name=file.filename,
        storage_key=key,
        size_bytes=len(raw),
        page_count=n,
    )
    db.add(rec)
    db.commit()
    return UploadResponse(fileId=file_id, fileName=file.filename, pageCount=n)


@router.post("/api/jobs", response_model=JobCreateResponse)
def create_job(
    body: JobCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    f = db.query(FileRecord).filter(FileRecord.id == body.fileId).first()
    if not f:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "fileId"})
    user_id = ensure_local_user(db)
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        user_id=user_id,
        file_id=f.id,
        status="queued",
        progress_percent=0,
        current_step="queued",
    )
    db.add(job)
    db.commit()
    out_fmt = list(body.outputFormats or ["png", "pdf", "json", "csv"])
    if "png" not in out_fmt:
        out_fmt.insert(0, "png")
    background_tasks.add_task(
        _run_job_background,
        job_id,
        body.pageSelectionMode,
        list(body.pageNumbers or []),
        out_fmt,
    )
    return JobCreateResponse(jobId=job_id, status="queued")


@router.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    err = None
    if job.status == "failed" and job.error_code:
        err = {"code": job.error_code, "message": job.error_message or ""}
    return JobStatusResponse(
        jobId=job.id,
        fileId=job.file_id,
        status=job.status,
        progress=job.progress_percent,
        step=job.current_step,
        createdAt=job.created_at.isoformat() + "Z" if job.created_at else None,
        updatedAt=job.updated_at.isoformat() + "Z" if job.updated_at else None,
        error=err,
    )


@router.get("/api/jobs/{job_id}/result", response_model=JobResultResponse)
def get_result(job_id: str, db: Session = Depends(get_db)) -> JobResultResponse:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if job.status != "completed":
        return JobResultResponse(jobId=job_id, status=job.status)

    file_rec = db.query(FileRecord).filter(FileRecord.id == job.file_id).first()
    outputs = {o.output_type: o.storage_key for o in db.query(JobOutput).filter(JobOutput.job_id == job_id)}
    segments = db.query(DuctSegment).filter(DuctSegment.job_id == job_id).all()
    measured = sum(1 for s in segments if s.length_value is not None)
    labeled = sum(1 for s in segments if s.size_text)
    pages_done = len({s.page_number for s in segments}) if segments else (file_rec.page_count if file_rec else 1)

    preview = f"/files/{outputs.get('annotated_png', '')}" if outputs.get("annotated_png") else None
    pdf_url = f"/files/{outputs.get('annotated_pdf', '')}" if outputs.get("annotated_pdf") else None
    exports = {}
    if sk := outputs.get("segments_json"):
        exports["json"] = f"/files/{sk}"
    if sk := outputs.get("segments_csv"):
        exports["csv"] = f"/files/{sk}"

    return JobResultResponse(
        jobId=job_id,
        status=job.status,
        previewUrl=preview,
        annotatedPdfUrl=pdf_url,
        exports=exports,
        summary=ResultSummary(
            pagesProcessed=pages_done,
            segmentsDetected=len(segments),
            segmentsMeasured=measured,
            labelsMatched=labeled,
        ),
    )


@router.get("/api/jobs/{job_id}/segments", response_model=SegmentsListResponse)
def get_segments(job_id: str, db: Session = Depends(get_db)) -> SegmentsListResponse:
    rows = db.query(DuctSegment).filter(DuctSegment.job_id == job_id).all()
    items = [
        SegmentItem(
            segmentId=r.segment_code,
            pageNumber=r.page_number,
            type=r.segment_type,
            shape=r.shape,
            sizeText=r.size_text,
            lengthFt=r.length_value,
            confidence=r.confidence_score,
            bbox=json.loads(r.bbox_json),
        )
        for r in rows
    ]
    return SegmentsListResponse(segments=items)


@router.get("/files/{full_path:path}")
def serve_file(full_path: str):
    path = settings.data_dir / full_path
    if not path.is_file():
        raise HTTPException(status_code=404)
    # prevent path traversal
    try:
        path.resolve().relative_to(settings.data_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403)
    media = "application/octet-stream"
    if path.suffix.lower() == ".png":
        media = "image/png"
    elif path.suffix.lower() == ".pdf":
        media = "application/pdf"
    elif path.suffix.lower() == ".json":
        media = "application/json"
    elif path.suffix.lower() == ".csv":
        media = "text/csv"
    return FileResponse(
        path,
        media_type=media,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.get("/api/admin/jobs")
def admin_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(50).all()
    return {
        "jobs": [
            {
                "jobId": j.id,
                "status": j.status,
                "fileId": j.file_id,
                "error": j.error_code,
                "createdAt": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ]
    }
