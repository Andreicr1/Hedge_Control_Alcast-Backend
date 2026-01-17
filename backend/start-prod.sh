#!/usr/bin/env sh
set -eu

PORT_VALUE="${PORT:-8000}"

read_secret_file() {
  # Usage: read_secret_file VAR_NAME
  # Precedence:
  # 1) existing env var
  # 2) <VAR_NAME>_FILE env var (path)
  # 3) /etc/secrets/<VAR_NAME>
  var_name="$1"

  # shellcheck disable=SC2086
  eval current_value="\${$var_name-}"
  if [ -n "${current_value}" ]; then
    return 0
  fi

  file_var_name="${var_name}_FILE"
  # shellcheck disable=SC2086
  eval file_path="\${$file_var_name-}"
  if [ -n "${file_path}" ] && [ -f "${file_path}" ]; then
    value=$(cat "${file_path}" | tr -d '\r')
    # shellcheck disable=SC2086
    eval export $var_name="\$value"
    return 0
  fi

  default_path="/etc/secrets/${var_name}"
  if [ -f "${default_path}" ]; then
    value=$(cat "${default_path}" | tr -d '\r')
    # shellcheck disable=SC2086
    eval export $var_name="\$value"
    return 0
  fi
}

# Render Secret Files support
read_secret_file DATABASE_URL || true
read_secret_file SECRET_KEY || true
read_secret_file CORS_ORIGINS || true

if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  echo "[startup] Running alembic migrations..."
  alembic upgrade head
else
  echo "[startup] Skipping migrations (set RUN_MIGRATIONS_ON_START=true to enable)."
fi

echo "[startup] Starting API on port ${PORT_VALUE}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_VALUE}"
