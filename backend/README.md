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

## Demo seed: LME prices (dev only)

If the Dashboard shows "Sem dados" for LME widgets, your database likely has no rows in `lme_prices`.

To generate a small demo dataset locally (so charts/live cards render), run from `backend/`:

- `python scripts/seed_lme_prices.py --days 120`

This script uses the configured `DATABASE_URL` (from `.env`). It is intended for dev only.

## LME ingest: Excel -> API (automation-friendly)

For real market data (not synthetic seed), use the operational script that reads your local `market.xlsx`
and POSTs JSON into the backend ingestion endpoint:

- `python scripts/ingest_lme_from_excel.py --xlsx "C:\\path\\to\\market.xlsx" --api-base-url "https://<your-render>/api" --token "<INGEST_TOKEN>"`

Notes:

- If your Excel export has a title row above headers, try `--header-row 2`.
- If you don't have a reliable intraday Quotes sheet, add `--also-live-from-history`.
- For scheduled runs on Windows Task Scheduler, copy `scripts/run_ingest_lme.ps1.example` to a local-only
  `scripts/run_ingest_lme.ps1` and schedule it (do not commit secrets/tokens).

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

