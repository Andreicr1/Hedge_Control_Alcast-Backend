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
    echo "[startup] ${var_name} already set via environment."
    return 0
  fi

  file_var_name="${var_name}_FILE"
  # shellcheck disable=SC2086
  eval file_path="\${$file_var_name-}"
  if [ -n "${file_path}" ] && [ -f "${file_path}" ]; then
    value=$(cat "${file_path}" | tr -d '\r')
    # shellcheck disable=SC2086
    eval export $var_name="\$value"
    echo "[startup] Loaded ${var_name} from ${file_path}."
    return 0
  fi

  default_path="/etc/secrets/${var_name}"
  if [ -f "${default_path}" ]; then
    value=$(cat "${default_path}" | tr -d '\r')
    # shellcheck disable=SC2086
    eval export $var_name="\$value"
    echo "[startup] Loaded ${var_name} from ${default_path}."
    return 0
  fi
}

is_weak_secret_key() {
  # Consider placeholders/unsafe defaults weak
  v=$(printf "%s" "${1-}" | tr -d '\r' | tr -d '\n' | sed 's/^ *//;s/ *$//')
  if [ -z "${v}" ]; then
    return 0
  fi
  case "${v}" in
    sua-chave-secreta*|SUA-CHAVE-SECRETA*|change-me|CHANGE-ME|secret|SECRET)
      return 0
      ;;
  esac
  return 1
}

require_non_empty() {
  var_name="$1"
  hint="$2"
  # shellcheck disable=SC2086
  eval current_value="\${$var_name-}"
  if [ -z "${current_value}" ]; then
    echo "[startup] ERROR: ${var_name} is not set. ${hint}" 1>&2
    exit 1
  fi
}

# Render Secret Files support
read_secret_file DATABASE_URL || true
read_secret_file SECRET_KEY || true
read_secret_file CORS_ORIGINS || true

# Fail fast with a clear message (avoids long Pydantic traceback on import)
require_non_empty DATABASE_URL "Create a Render Secret File named DATABASE_URL (or set DATABASE_URL_FILE)."
require_non_empty SECRET_KEY "Create a Render Secret File named SECRET_KEY (or set SECRET_KEY_FILE)."

if is_weak_secret_key "${SECRET_KEY-}"; then
  echo "[startup] ERROR: SECRET_KEY is missing or looks like a placeholder. Set a long random value (>= 32 chars)." 1>&2
  exit 1
fi

if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  echo "[startup] Running alembic migrations..."
  alembic upgrade head
else
  echo "[startup] Skipping migrations (set RUN_MIGRATIONS_ON_START=true to enable)."
fi

echo "[startup] Starting API on port ${PORT_VALUE}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT_VALUE}"
