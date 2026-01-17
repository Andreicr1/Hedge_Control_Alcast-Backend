#!/usr/bin/env sh
set -eu

PORT_VALUE="${PORT:-8000}"

if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  echo "[startup] Running alembic migrations..."
  alembic upgrade head
else
  echo "[startup] Skipping migrations (set RUN_MIGRATIONS_ON_START=true to enable)."
fi

echo "[startup] Starting API on port ${PORT_VALUE}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_VALUE}"
