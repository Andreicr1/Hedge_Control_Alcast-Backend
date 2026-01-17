# Hedge Control Alcast - Backend

## Dev setup (supported)

**Supported Python:** 3.11.x (CI is the source of truth).  
**Supported Node.js:** 20.x (only if you use any Node tooling in this folder).

### Environment file (local-only)

- Copy `.env.example` to `.env` **locally**.
- Do not commit `.env` (it contains credentials/secrets).
- Provide values for at least:
  - `DATABASE_URL`
  - `SECRET_KEY`

Notes:

- In production (`ENVIRONMENT=production`), you must explicitly set `CORS_ORIGINS`.
- API docs are enabled only in dev/test by default. You can override with `ENABLE_DOCS=true|false`.

### Windows quick start

1. Create + activate a Python 3.11 virtualenv

- `py -3.11 -m venv .venv`
- `.\.venv\Scripts\activate`

1. Install dependencies

- `python -m pip install -r requirements-dev.txt`

1. Configure environment

- Copy `.env.example` → `.env` and fill the values.

1. Run the API

- `uvicorn app.main:app --reload --port 8000`

If you prefer, you can use the helper scripts:

- `setup-dev.bat`
- `start-dev.bat`

(Ensure those scripts run with Python 3.11 on PATH.)

## Quality Gates

### Pre-commit Hook (recommended)

Install the pre-commit hook to catch lint issues before commit:

```bash
# From backend/ directory
bash scripts/setup-hooks.sh
```

### Manual Quality Commands

```bash
# Full quality check (lint + format + tests)
./scripts/quality.sh

# Lint only (faster)
./scripts/quality.sh --lint

# Autofix lint issues
./scripts/quality.sh --fix

# Tests only
./scripts/quality.sh --test
```

### CI/CD

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs the full `quality.sh` on every push and PR.

