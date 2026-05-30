#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/backend"
"$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir "$ROOT/backend" --reload --reload-dir "$ROOT/backend" &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
cd "$ROOT/frontend"
npm run dev
