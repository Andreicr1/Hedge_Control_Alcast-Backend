#!/usr/bin/env bash
set -euo pipefail

# Start Backend Development Server (Git Bash / WSL-friendly)
# Runs from any working directory.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${UVICORN_HOST:-127.0.0.1}"
PORT="${UVICORN_PORT:-8001}"

# Prefer .venv311 if present, else .venv.
if [[ -x ".venv311/Scripts/python.exe" ]]; then
  PY_EXE=".venv311/Scripts/python.exe"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
  PY_EXE=".venv/Scripts/python.exe"
else
  echo "ERROR: Virtual environment not found (.venv311 or .venv)." >&2
  echo "Run ./setup-dev.sh (Git Bash) or .\\setup-dev.bat (PowerShell) first." >&2
  exit 1
fi

echo "================================"
echo "Starting Backend Server (sh)"
echo "================================"
echo

echo "Backend:  http://$HOST:$PORT"
echo "API Docs: http://$HOST:$PORT/docs"
echo

"$PY_EXE" -m uvicorn app.main:app \
  --reload \
  --host "$HOST" \
  --port "$PORT" \
  --app-dir "$ROOT_DIR" \
  --env-file "$ROOT_DIR/.env"
