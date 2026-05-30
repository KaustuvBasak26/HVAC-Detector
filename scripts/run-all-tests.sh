#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(
  cd "$ROOT/backend"
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    "$ROOT/.venv/bin/python" -m pytest tests/
  else
    python3 -m pytest tests/
  fi
)
(
  cd "$ROOT/frontend"
  npm test
)
