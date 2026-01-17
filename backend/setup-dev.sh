#!/usr/bin/env bash
set -euo pipefail

# Setup Backend Development Environment (Git Bash / WSL-friendly)
# Runs from any working directory.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "================================"
echo "Backend Development Setup (sh)"
echo "================================"
echo

# Prefer Python 3.11 via Windows launcher if present.
if command -v py >/dev/null 2>&1; then
  if ! py -3.11 -c "import sys; print(sys.version.split()[0])" >/dev/null 2>&1; then
    echo "ERROR: Python 3.11 is required but was not found via 'py -3.11'." >&2
    echo "Install Python 3.11.x and ensure py.exe is available." >&2
    exit 1
  fi
  PY_LAUNCHER=(py -3.11)
else
  echo "ERROR: 'py' launcher not found. Install Python 3.11 and enable py.exe." >&2
  exit 1
fi

VENV_DIR=".venv"
PY_EXE="$VENV_DIR/Scripts/python.exe"

if [[ ! -x "$PY_EXE" ]]; then
  echo "[1/5] Creating virtual environment..."
  "${PY_LAUNCHER[@]}" -m venv "$VENV_DIR"
else
  echo "[1/5] Virtual environment already exists."
fi

echo "[2/5] Activating virtual environment..."
# shellcheck disable=SC1091
source "$VENV_DIR/Scripts/activate"

echo "[3/5] Installing dependencies..."
"$PY_EXE" -m pip install -r requirements-dev.txt

echo "[4/5] Running database migrations..."
"$PY_EXE" -m alembic upgrade head

echo "[5/5] Seeding users..."
"$PY_EXE" -m app.scripts.seed_users

echo
echo "================================"
echo "Setup completed successfully!"
echo "================================"
echo
echo "To start the backend server:"
echo "  ./start-dev.sh"
echo
echo "Overrides (optional):"
echo "  UVICORN_PORT=8000 UVICORN_HOST=0.0.0.0 ./start-dev.sh"
