# HVAC Duct Detector

Web application that uploads **HVAC mechanical drawings** (PDF), detects duct-like geometry on the plan, reads nearby **size labels** and **scale** text where possible, estimates **segment lengths**, and produces **annotated PNG/PDF** plus **JSON/CSV** exports.

The implementation follows the project’s high-level and low-level design: FastAPI backend with a modular PDF/vision pipeline, SQLite for job metadata, local file storage under `data/`, and a React (Vite) frontend for upload, status, preview with zoom/pan, and downloads.

## Requirements

- **Python** 3.11+ (3.13 tested)
- **Node.js** 18+ and npm (for the frontend)
- **Docker** and Docker Compose v2 (optional, for running the full stack in containers)

## Setup

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

For **backend tests**, also install dev dependencies:

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
```

## Run

### Docker (single command)

From the **repository root** (the folder that contains `docker-compose.yml`):

```bash
docker compose up --build
```

Do **not** pass a service name (for example `docker compose up backend` only starts the API and will skip the UI). Use `docker compose up --build` or `docker compose up --build backend frontend` so both services run.

Published ports:

| Host | Service |
|------|---------|
| [http://localhost:8080](http://localhost:8080) | **Web UI** (nginx → static app + proxy to the API) |
| [http://localhost:8000](http://localhost:8000) | **API only** (optional; useful for debugging or `curl` — the browser should normally use **8080** so `/api` and `/files` stay same-origin) |

Check that both containers are up and ports are bound:

```bash
docker compose ps
```

You should see `0.0.0.0:8080->80/tcp` on **frontend** and `0.0.0.0:8000->8000/tcp` on **backend**. If a port is already in use on your machine, edit the `ports:` mappings in `docker-compose.yml`.

The frontend waits until the backend passes a health check on `/api/health`, then starts nginx. Uploads up to **100MB** are allowed at the proxy. Data lives in the **`hvac_data`** volume (`HVAC_DATA_DIR=/data` in the backend container).

### Local development (two terminals)

You need **two terminals** (API and UI).

**Terminal 1 — API** (port 8000):

```bash
export PYTHONPATH=backend
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend
```

**Terminal 2 — frontend** (port 5173):

```bash
cd frontend && npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The dev server proxies `/api` and `/files` to the backend, so uploads and previews work without extra CORS setup.

**Optional:** from the repo root, `scripts/dev.sh` starts the API in the background and then runs the Vite dev server (requires the same setup steps above).

## Tests

**Backend** (pytest; `backend/pytest.ini` sets `pythonpath` so imports resolve when run from `backend/`):

```bash
cd backend && ../.venv/bin/python -m pytest tests/
```

**Frontend** (Vitest):

```bash
cd frontend && npm test
```

**Both** (uses `.venv` at the repo root if present):

```bash
./scripts/run-all-tests.sh
```

## Usage

1. Choose a PDF mechanical plan and click **Upload & run**.
2. Wait until the job status shows **completed**.
3. Use the **Preview** panel to zoom and pan the annotated image.
4. Download **annotated PDF**, **segments.json**, or **segments.csv** as needed.

Uploaded files and job outputs are stored under `data/` when running locally (see `.gitignore`); the SQLite database is `data/app.db`. With **Docker Compose**, the same layout exists inside the container under `/data`, backed by the `hvac_data` volume.

## Golden test assets

| Asset | Role |
|-------|------|
| `data/testset2.pdf` | **Minimum realistic input** — mechanical floor plan used to validate the duct pipeline (replace by copying your own MEP PDF over this path if needed). |
| `Sample annotation.png` | **Expected output style** — dark saturated blue duct strokes + DUCT SCHEDULE (human reference; tune e.g. `HVAC_ANNOTATION_CENTERLINE_ALPHA`, `HVAC_ANNOTATION_CENTERLINE_WIDTH_SCALE`, `HVAC_ANNOTATION_DUCT_BLUE_B` / `_G` / `_R`). |

Quick check from the repo root (after venv + `pip install -r backend/requirements.txt`):

```bash
export PYTHONPATH=backend
.venv/bin/python scripts/verify_testset2.py
```

The old `data/test_min.pdf` stub is removed; it did not represent real MEP geometry.

## Machine learning (optional)

There is **no ready-made Hugging Face model** that outputs HVAC duct polylines for arbitrary rasterized MEP plans. Practical options:

1. **Fine-tune** a segmentation model (SegFormer, Mask2Former, U-Net, SAM decoder head) on masks derived from your own markup (e.g. rasterize `Sample annotation.png` aligned to `testset2.pdf` pages).
2. **Deploy** that model behind [Hugging Face Inference Endpoints](https://huggingface.co/inference-endpoints), **Roboflow**, **Modal**, **Replicate**, or your own FastAPI worker.
3. Point this app at it with **`HVAC_ML_SEGMENTATION_URL`** (and optional **`HVAC_ML_SEGMENTATION_BEARER_TOKEN`**). The pipeline POSTs the **plan-crop PNG** (`multipart` field `plan`) and expects JSON as documented in `backend/app/processing/ml_segmentation_remote.py`. If the call fails or returns no segments, it **falls back** to the built-in heuristic detector.

Vision-only “chat” APIs (OpenAI, Anthropic, etc.) are poor fits for precise vector geometry on large sheets.

## Configuration

Environment variables use the prefix `HVAC_` (see `backend/app/core/config.py`). Examples:

| Variable | Purpose |
|----------|---------|
| `HVAC_RENDER_DPI` | Rasterization DPI (default `200`) |
| `HVAC_DEFAULT_FEET_PER_DRAWING_INCH` | Fallback scale when no scale text is found; feet of real world per inch on the sheet (default `4.0`, roughly ¼″ = 1′-0″). Set to omit fallback behavior only by changing code or extending config. |
| `HVAC_MAX_UPLOAD_SIZE_MB` | Upload limit (default `100`) |
| `HVAC_ML_SEGMENTATION_URL` | Optional duct segmentation HTTP API (see **Machine learning** above). |
| `HVAC_ML_SEGMENTATION_BEARER_TOKEN` | Bearer token for that API (e.g. HF `hf_...`). |
| *(see code)* | `cors_origins` in `backend/app/core/config.py` if the UI is not on `localhost:5173` |

## API overview

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/files/upload` | Multipart PDF upload |
| `POST` | `/api/jobs` | Queue processing for a `fileId` |
| `GET` | `/api/jobs/{jobId}` | Job status and progress |
| `GET` | `/api/jobs/{jobId}/result` | Preview URLs, exports, summary |
| `GET` | `/api/jobs/{jobId}/segments` | Detected segments and metadata |
| `GET` | `/files/...` | Static download of generated artifacts under `data/` |
| `GET` | `/api/admin/jobs` | Recent jobs (simple admin view) |

## Production build (frontend only)

```bash
cd frontend && npm run build
```

Serve `frontend/dist` with any static host; configure that host to reverse-proxy `/api` and `/files` to the FastAPI server (same pattern as `frontend/nginx.conf` in the Docker image), or set the frontend to call the API’s absolute origin.

## Limitations

Detection uses **classical image processing** (not a trained model), so results depend on line quality, cropping, and drawing style. Supply vs. return typing is heuristic. For best results on a specific sheet set, tune parameters or extend the pipeline in `backend/app/processing/`.
