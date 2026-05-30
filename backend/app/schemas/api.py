from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    fileId: str
    fileName: str
    status: str = "uploaded"
    pageCount: int


class JobCreateRequest(BaseModel):
    fileId: str
    pageSelectionMode: str = "all"
    pageNumbers: list[int] = Field(default_factory=list)
    outputFormats: list[str] = Field(default_factory=lambda: ["png", "pdf", "json"])


class JobCreateResponse(BaseModel):
    jobId: str
    status: str = "queued"
    viewerToken: str | None = None


class JobStatusResponse(BaseModel):
    jobId: str
    fileId: str
    status: str
    progress: int = 0
    step: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    error: dict | None = None


class ResultSummary(BaseModel):
    pagesProcessed: int
    segmentsDetected: int
    segmentsMeasured: int
    labelsMatched: int


class JobResultResponse(BaseModel):
    jobId: str
    status: str
    previewUrl: str | None = None
    annotatedPdfUrl: str | None = None
    exports: dict[str, str] = Field(default_factory=dict)
    summary: ResultSummary | None = None


class SegmentItem(BaseModel):
    segmentId: str
    pageNumber: int
    type: str
    shape: str
    sizeText: str | None
    lengthFt: float | None
    confidence: float
    bbox: list[int]


class SegmentsListResponse(BaseModel):
    segments: list[SegmentItem]


class ErrorResponse(BaseModel):
    error: dict
