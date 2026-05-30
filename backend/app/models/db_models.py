import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), default="local@localhost")
    name: Mapped[str] = mapped_column(String(255), default="Local User")
    role: Mapped[str] = mapped_column(String(32), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    original_name: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="file")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    file: Mapped["FileRecord"] = relationship(back_populates="jobs")
    segments: Mapped[list["DuctSegment"]] = relationship(back_populates="job")
    outputs: Mapped[list["JobOutput"]] = relationship(back_populates="job")


class DuctSegment(Base):
    __tablename__ = "duct_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    page_number: Mapped[int] = mapped_column(Integer)
    segment_code: Mapped[str] = mapped_column(String(32))
    segment_type: Mapped[str] = mapped_column(String(32), default="supply")
    shape: Mapped[str] = mapped_column(String(32), default="rectangular")
    size_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    diameter_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_unit: Mapped[str] = mapped_column(String(16), default="ft")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    bbox_json: Mapped[str] = mapped_column(Text)
    polyline_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="segments")


class JobOutput(Base):
    __tablename__ = "job_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"))
    output_type: Mapped[str] = mapped_column(String(32))
    storage_key: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="outputs")
