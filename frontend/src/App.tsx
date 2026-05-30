import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  TransformComponent,
  TransformWrapper,
  useTransformComponent,
} from "react-zoom-pan-pinch";

import {
  compareSegments,
  confidenceBarClass,
  formatJobStep,
  type SegmentRow,
  type SortDir,
  type SortKey,
} from "./jobUtils";

type JobStatus = {
  jobId: string;
  status: string;
  progress: number;
  step: string | null;
  error?: { code: string; message: string };
};

type Result = {
  previewUrl: string | null;
  annotatedPdfUrl: string | null;
  exports: Record<string, string>;
  summary?: {
    segmentsDetected: number;
    segmentsMeasured: number;
    labelsMatched: number;
  };
};

type TypeFilter = "all" | "supply" | "return";

type NavPanel = "ingest" | "register";

function getFullscreenElement(): Element | null {
  const d = document as Document & { webkitFullscreenElement?: Element | null };
  return document.fullscreenElement ?? d.webkitFullscreenElement ?? null;
}

async function togglePreviewFullscreen(el: HTMLElement | null): Promise<void> {
  if (!el) return;
  const doc = document as Document & { webkitExitFullscreen?: () => Promise<void> };
  const node = el as HTMLElement & { webkitRequestFullscreen?: () => Promise<void> };
  const current = getFullscreenElement();
  try {
    if (current === el) {
      if (document.exitFullscreen) await document.exitFullscreen();
      else await doc.webkitExitFullscreen?.();
    } else {
      if (el.requestFullscreen) await el.requestFullscreen();
      else {
        node.webkitRequestFullscreen?.();
      }
    }
  } catch (err) {
    console.error("Fullscreen failed:", err);
  }
}

function TypeBadge({ type }: { type: string }) {
  const t = type.toLowerCase();
  const cls =
    t === "supply"
      ? "badge-type--supply"
      : t === "return"
        ? "badge-type--return"
        : "badge-type--other";
  return <span className={`badge-type ${cls}`}>{type}</span>;
}

function PreviewZoomReadout() {
  const scale = useTransformComponent((ctx) => ctx.state.scale);
  return <span className="preview-zoom-readout">{Math.round(scale * 100)}%</span>;
}

function IconMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 19V5a1 1 0 011-1h12a1 1 0 011 1v14l-7-3.5L4 19z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconNavIngest() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconNavTable() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18M9 21V9" />
    </svg>
  );
}

function IconDownload() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconSearch() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" strokeLinecap="round" />
    </svg>
  );
}

function IconKpiSegments() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 19V5M20 19V5M9 19V9M15 19v-4" strokeLinecap="round" />
    </svg>
  );
}

function IconKpiMeasure() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 21h18M5 21V7l4-4 4 4 4-4 4 4v14" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconKpiLabels() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 6h18M3 12h12M3 18h8" strokeLinecap="round" />
    </svg>
  );
}

function IconZoomIn() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-3.5-3.5M11 8v6M8 11h6" strokeLinecap="round" />
    </svg>
  );
}

function IconZoomOut() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-3.5-3.5M8 11h6" strokeLinecap="round" />
    </svg>
  );
}

function IconReset() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M3 12a9 9 0 101.9-4" strokeLinecap="round" />
      <path d="M3 4v4h4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconFit() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path
        d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconFullscreen() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path
        d="M8 3H5a2 2 0 00-2 2v3M21 8V5a2 2 0 00-2-2h-3M3 16v3a2 2 0 002 2h3M16 21h3a2 2 0 002-2v-3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconExitFullscreen() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path
        d="M8 3v3a2 2 0 01-2 2H3M16 3h3a2 2 0 012 2v3M8 21H5a2 2 0 01-2-2v-3M21 16v3a2 2 0 01-2 2h-3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

type ZoomCtrl = {
  zoomIn: (step?: number) => void;
  zoomOut: (step?: number) => void;
  resetTransform: () => void;
  centerView: (scale?: number) => void;
};

function PreviewToolbar({
  ctrl,
  previewFullscreen,
  onToggleFullscreen,
}: {
  ctrl: ZoomCtrl;
  previewFullscreen: boolean;
  onToggleFullscreen: () => void;
}) {
  return (
    <div className="preview-toolbar">
      <button
        type="button"
        className="btn btn--ghost btn--icon"
        onClick={() => ctrl.zoomOut()}
        aria-label="Zoom out"
      >
        <IconZoomOut />
      </button>
      <button
        type="button"
        className="btn btn--ghost btn--icon"
        onClick={() => ctrl.zoomIn()}
        aria-label="Zoom in"
      >
        <IconZoomIn />
      </button>
      <span className="preview-toolbar__sep" aria-hidden />
      <button
        type="button"
        className="btn btn--ghost btn--icon"
        onClick={() => ctrl.resetTransform()}
        aria-label="Reset pan and zoom"
      >
        <IconReset />
      </button>
      <button
        type="button"
        className="btn btn--ghost btn--icon"
        onClick={() => ctrl.centerView(0.32)}
        aria-label="Fit drawing in panel"
        title="Fit drawing in panel"
      >
        <IconFit />
      </button>
      <button
        type="button"
        className="btn btn--ghost btn--icon"
        onClick={onToggleFullscreen}
        aria-label={previewFullscreen ? "Exit full screen" : "Enter full screen"}
        aria-pressed={previewFullscreen}
        title={previewFullscreen ? "Exit full screen" : "Full screen preview"}
      >
        {previewFullscreen ? <IconExitFullscreen /> : <IconFullscreen />}
      </button>
      <PreviewZoomReadout />
      <span className="preview-hint-inline">Scroll to zoom · drag to pan</span>
    </div>
  );
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [segments, setSegments] = useState<SegmentRow[]>([]);
  const [previewNonce, setPreviewNonce] = useState(0);
  const [segmentQuery, setSegmentQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("segmentId");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [activeNav, setActiveNav] = useState<NavPanel>("ingest");
  const [previewFullscreen, setPreviewFullscreen] = useState(false);

  const previewCardRef = useRef<HTMLElement | null>(null);
  const ingestRef = useRef<HTMLElement | null>(null);
  const registerRef = useRef<HTMLElement | null>(null);

  const poll = useCallback(async (id: string) => {
    const r = await fetch(`/api/jobs/${id}`);
    const j = (await r.json()) as JobStatus;
    setStatus(j);
    if (j.status === "completed") {
      const rr = await fetch(`/api/jobs/${id}/result`);
      const res = (await rr.json()) as Result & { jobId: string; status: string };
      setPreviewNonce(Date.now());
      setResult({
        previewUrl: res.previewUrl,
        annotatedPdfUrl: res.annotatedPdfUrl,
        exports: res.exports || {},
        summary: (res as { summary?: Result["summary"] }).summary,
      });
      const sr = await fetch(`/api/jobs/${id}/segments`);
      const sj = (await sr.json()) as { segments: SegmentRow[] };
      setSegments(sj.segments || []);
      setBusy(false);
      return true;
    }
    if (j.status === "failed") {
      setBusy(false);
      setMsg(j.error?.message || "Job failed");
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    if (!jobId || !busy) return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      const done = await poll(jobId);
      return done;
    };
    void tick();
    const t = setInterval(async () => {
      if (cancelled) return;
      const done = await tick();
      if (done) clearInterval(t);
    }, 1200);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [jobId, busy, poll]);

  useEffect(() => {
    const onFs = () => {
      setPreviewFullscreen(getFullscreenElement() === previewCardRef.current);
    };
    document.addEventListener("fullscreenchange", onFs);
    document.addEventListener("webkitfullscreenchange", onFs);
    return () => {
      document.removeEventListener("fullscreenchange", onFs);
      document.removeEventListener("webkitfullscreenchange", onFs);
    };
  }, []);

  const onTogglePreviewFullscreen = useCallback(() => {
    void togglePreviewFullscreen(previewCardRef.current);
  }, []);

  const scrollToIngest = useCallback(() => {
    ingestRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveNav("ingest");
  }, []);

  const scrollToRegister = useCallback(() => {
    registerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveNav("register");
  }, []);

  const toggleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir("asc");
    }
  };

  const filteredSegments = useMemo(() => {
    const q = segmentQuery.trim().toLowerCase();
    let rows = segments.filter((s) => {
      if (typeFilter !== "all" && s.type.toLowerCase() !== typeFilter) return false;
      if (!q) return true;
      const hay = `${s.segmentId} ${s.type} ${s.sizeText ?? ""}`.toLowerCase();
      return hay.includes(q);
    });
    rows = [...rows].sort((a, b) => compareSegments(a, b, sortKey, sortDir));
    return rows;
  }, [segments, segmentQuery, typeFilter, sortKey, sortDir]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setResult(null);
    setSegments([]);
    setStatus(null);
    if (!file) {
      setMsg("Choose a PDF file first (click the dashed area), then click Run analysis.");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const up = await fetch("/api/files/upload", { method: "POST", body: fd });
      if (!up.ok) {
        const err = await up.json().catch(() => ({}));
        const d = (err as { detail?: unknown }).detail;
        let message = "Upload failed — is the API running on port 8000?";
        if (typeof d === "string") message = d;
        else if (d && typeof d === "object" && "message" in d)
          message = String((d as { message?: string }).message);
        setMsg(message);
        setBusy(false);
        return;
      }
      const uj = (await up.json()) as { fileId: string };
      const cr = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fileId: uj.fileId,
          pageSelectionMode: "all",
          outputFormats: ["png", "pdf", "json", "csv"],
        }),
      });
      if (!cr.ok) {
        setMsg("Could not start job");
        setBusy(false);
        return;
      }
      const cj = (await cr.json()) as { jobId: string };
      setJobId(cj.jobId);
    } catch (err) {
      console.error(err);
      setMsg(
        err instanceof Error
          ? `${err.message} (check that the backend is running and the dev proxy is active).`
          : "Request failed — check the browser console and that uvicorn is on port 8000."
      );
      setBusy(false);
    }
  }

  const previewUrl = result?.previewUrl || null;
  const previewSrc =
    previewUrl && jobId
      ? `${previewUrl}?v=${encodeURIComponent(jobId)}&n=${previewNonce}`
      : previewUrl;

  const statusPillClass = busy ? "pill pill--busy" : "pill pill--live";
  const statusPillLabel = busy ? "Processing" : "Ready";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__brand">
          <div className="topbar__mark" aria-hidden>
            <IconMark />
          </div>
          <div className="topbar__titles">
            <p className="topbar__product">Duct Analyzer</p>
            <p className="topbar__tagline">HVAC takeoff · mechanical plans</p>
          </div>
        </div>
        <div className="topbar__right">
          <span className={statusPillClass}>
            <span className="pill__dot" />
            {statusPillLabel}
          </span>
        </div>
      </header>

      <div className="shell__body">
        <aside className="sidebar" aria-label="Workspace">
          <div className="sidebar__label">Workspace</div>
          <button
            type="button"
            className={`nav-item${activeNav === "ingest" ? " nav-item--active" : ""}`}
            onClick={scrollToIngest}
          >
            <IconNavIngest />
            Ingest &amp; analyze
          </button>
          <button
            type="button"
            className={`nav-item${activeNav === "register" ? " nav-item--active" : ""}`}
            onClick={scrollToRegister}
          >
            <IconNavTable />
            Segment register
          </button>
        </aside>

        <main className="main">
          <header className="page-header" ref={ingestRef} id="workspace-ingest">
            <h1 className="page-header__title">Mechanical drawing analysis</h1>
            <p className="page-header__lead">
              Upload a mechanical PDF. The pipeline detects duct runs, matches nearby size callouts,
              estimates lengths from scale text (or a default drawing scale), and produces highlighted
              previews plus PDF, JSON, and CSV exports.
            </p>
          </header>

          <form className="card card--upload" onSubmit={onSubmit} noValidate>
            <label className="file-input__label">
              <input
                className="sr-only-input"
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                aria-label="Choose PDF file"
              />
              <span>{file ? file.name : "Choose PDF…"}</span>
            </label>
            <button className="btn" type="submit" disabled={busy}>
              {busy ? "Processing…" : "Run analysis"}
            </button>
          </form>

          {msg && <div className="alert">{msg}</div>}

          {busy && jobId && !status && (
            <p className="status-line" aria-live="polite">
              <strong>Connecting…</strong> — waiting for job status
            </p>
          )}

          {status && status.status !== "completed" && status.status !== "failed" && (
            <div className="job-progress card" role="status" aria-live="polite" aria-busy="true">
              <div className="job-progress__head">
                <span className="status-line">
                  Status: <strong>{status.status}</strong>
                  {typeof status.progress === "number" ? ` — ${status.progress}%` : ""}
                </span>
                {formatJobStep(status.step) && (
                  <span className="job-progress__step">{formatJobStep(status.step)}</span>
                )}
              </div>
              {typeof status.progress === "number" && (
                <div className="job-progress__bar" aria-hidden="true">
                  <div
                    className="job-progress__fill"
                    style={{ width: `${Math.min(100, Math.max(0, status.progress))}%` }}
                  />
                </div>
              )}
            </div>
          )}

          {result?.summary && (
            <div className="kpi-grid">
              <div className="kpi">
                <div className="kpi__icon" aria-hidden>
                  <IconKpiSegments />
                </div>
                <div className="kpi__body">
                  <div className="kpi__val">{result.summary.segmentsDetected}</div>
                  <div className="kpi__lbl">Segments detected</div>
                </div>
              </div>
              <div className="kpi">
                <div className="kpi__icon" aria-hidden>
                  <IconKpiMeasure />
                </div>
                <div className="kpi__body">
                  <div className="kpi__val">{result.summary.segmentsMeasured}</div>
                  <div className="kpi__lbl">With length</div>
                </div>
              </div>
              <div className="kpi">
                <div className="kpi__icon" aria-hidden>
                  <IconKpiLabels />
                </div>
                <div className="kpi__body">
                  <div className="kpi__val">{result.summary.labelsMatched}</div>
                  <div className="kpi__lbl">Size labels matched</div>
                </div>
              </div>
            </div>
          )}

          {previewSrc && (
            <section ref={previewCardRef} className="card preview-card">
              <div className="preview-card__inner">
                <div className="section-head" style={{ marginBottom: "0.5rem" }}>
                  <div>
                    <h2 className="section-title">Drawing preview</h2>
                    <p className="section-desc">
                      Server-rendered PNG: duct lines and D-* tags are drawn together. Sizes and
                      lengths also appear in the register below.
                    </p>
                  </div>
                </div>
              </div>
              <TransformWrapper
                initialScale={0.32}
                minScale={0.08}
                maxScale={5}
                centerOnInit
                doubleClick={{ mode: "reset" }}
              >
                {(ctrl) => (
                  <>
                    <PreviewToolbar
                      ctrl={ctrl}
                      previewFullscreen={previewFullscreen}
                      onToggleFullscreen={onTogglePreviewFullscreen}
                    />
                    <div className="preview-wrap">
                      <TransformComponent
                        wrapperStyle={{ width: "100%", height: "100%" }}
                        contentStyle={{ width: "100%", height: "100%" }}
                      >
                        <img
                          key={`${jobId}-${previewNonce}`}
                          src={previewSrc}
                          alt="Annotated drawing with duct highlights"
                          style={{ display: "block", maxWidth: "100%", height: "auto" }}
                        />
                      </TransformComponent>
                    </div>
                  </>
                )}
              </TransformWrapper>
            </section>
          )}

          {result &&
            (result.annotatedPdfUrl || Object.keys(result.exports || {}).length > 0) && (
              <section className="card">
                <div className="section-head">
                  <div>
                    <h2 className="section-title">Exports</h2>
                    <p className="section-desc">Download annotated deliverables and structured data.</p>
                  </div>
                </div>
                <ul className="download-list">
                  {result.annotatedPdfUrl && (
                    <li>
                      <a
                        href={`${result.annotatedPdfUrl}?v=${encodeURIComponent(jobId || "")}&n=${previewNonce}`}
                        download
                      >
                        <IconDownload />
                        Annotated PDF
                      </a>
                    </li>
                  )}
                  {result.exports.json && (
                    <li>
                      <a
                        href={`${result.exports.json}?v=${encodeURIComponent(jobId || "")}&n=${previewNonce}`}
                        download
                      >
                        <IconDownload />
                        segments.json
                      </a>
                    </li>
                  )}
                  {result.exports.csv && (
                    <li>
                      <a
                        href={`${result.exports.csv}?v=${encodeURIComponent(jobId || "")}&n=${previewNonce}`}
                        download
                      >
                        <IconDownload />
                        segments.csv
                      </a>
                    </li>
                  )}
                </ul>
              </section>
            )}

          <section ref={registerRef} className="card" id="segment-register">
            <div className="section-head">
              <div>
                <h2 className="section-title">Segment register</h2>
                <p className="section-desc">
                  Filter and sort the detected duct inventory. Click column headers to sort.
                </p>
              </div>
            </div>

            {segments.length === 0 ? (
              <p className="register-empty">
                {result
                  ? "No segments were returned for this job. If you expected a table here, check the API response or run the analysis again."
                  : "Run an analysis above to populate the segment register. Use the sidebar link anytime to jump back to this section."}
              </p>
            ) : (
              <>
                <div className="segments-toolbar">
                  <label className="search-field">
                    <IconSearch />
                    <input
                      type="search"
                      placeholder="Search ID, type, size…"
                      value={segmentQuery}
                      onChange={(e) => setSegmentQuery(e.target.value)}
                      aria-label="Filter segments"
                    />
                  </label>
                  <div className="chip-group" role="group" aria-label="Filter by duct type">
                    {(
                      [
                        ["all", "All"],
                        ["supply", "Supply"],
                        ["return", "Return"],
                      ] as const
                    ).map(([val, label]) => (
                      <button
                        key={val}
                        type="button"
                        className={`chip${typeFilter === val ? " chip--on" : ""}`}
                        onClick={() => setTypeFilter(val)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <span className="segments-meta">
                    Showing {filteredSegments.length} of {segments.length}
                  </span>
                </div>

                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th scope="col" onClick={() => toggleSort("segmentId")}>
                          <span className="th-inner">
                            ID
                            {sortKey === "segmentId" && (
                              <span className="sort-ind">{sortDir === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th scope="col" onClick={() => toggleSort("type")}>
                          <span className="th-inner">
                            Type
                            {sortKey === "type" && (
                              <span className="sort-ind">{sortDir === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th scope="col" onClick={() => toggleSort("sizeText")}>
                          <span className="th-inner">
                            Size
                            {sortKey === "sizeText" && (
                              <span className="sort-ind">{sortDir === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th scope="col" onClick={() => toggleSort("lengthFt")}>
                          <span className="th-inner">
                            Length (ft)
                            {sortKey === "lengthFt" && (
                              <span className="sort-ind">{sortDir === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                        <th scope="col" onClick={() => toggleSort("confidence")}>
                          <span className="th-inner">
                            Confidence
                            {sortKey === "confidence" && (
                              <span className="sort-ind">{sortDir === "asc" ? "↑" : "↓"}</span>
                            )}
                          </span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSegments.map((s) => (
                        <tr key={s.segmentId}>
                          <td>
                            <strong style={{ fontWeight: 600 }}>{s.segmentId}</strong>
                          </td>
                          <td>
                            <TypeBadge type={s.type} />
                          </td>
                          <td>{s.sizeText ?? "—"}</td>
                          <td style={{ fontVariantNumeric: "tabular-nums" }}>
                            {s.lengthFt != null ? s.lengthFt.toFixed(2) : "—"}
                          </td>
                          <td>
                            <div className="conf-cell">
                              <div className="conf-bar" aria-hidden>
                                <div
                                  className={confidenceBarClass(s.confidence)}
                                  style={{
                                    width: `${Math.min(100, Math.max(0, s.confidence * 100))}%`,
                                  }}
                                />
                              </div>
                              <span className="conf-val">{s.confidence.toFixed(2)}</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
