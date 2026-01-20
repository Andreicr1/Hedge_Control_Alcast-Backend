# Deploy: Supabase (Postgres) + Render (FastAPI)

This is the Fly.io alternative for a stable remote backend:

- **DB:** Supabase Postgres
- **API:** Render Web Service

## Why Render

- Very stable always-on hosting with HTTPS and logs.
- Simple Docker deploy (matches local container behavior).

## 1) Supabase: get the DB connection string

From Supabase project settings:

- Copy the **connection string**.
- Ensure TLS is enabled: add `?sslmode=require`.

Notes:

- Use the exact connection string shown by Supabase (including user/host). If you use the Pooler host (`*.pooler.supabase.com`), keep the username format exactly as provided.
- Do not use SQLite for Supabase/Render deploys.

### If you see "max clients reached" (Supabase pooler)

If Render (or local dev) fails to boot with an error like:

- `FATAL: MaxClientsInSessionMode: max clients reached`

it usually means you are using the **Pooler in Session mode** and the app is opening too many connections.

Recommended fixes (pick one):

1) Prefer Supabase **Transaction pooler** connection string (best for web services)
	 - In Supabase → Database → Connection string, choose the pooler **Transaction** mode.
	 - Update `DATABASE_URL` in Render to that value.

2) Reduce SQLAlchemy pooling on the app side
	 - Set in Render env vars:
		 - `DB_POOL_SIZE=1`
		 - `DB_MAX_OVERFLOW=0`
	 - Optionally disable pooling entirely (useful with transaction poolers):
		 - `DB_USE_NULL_POOL=true`

Example:

- `postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require`

This repo normalizes `postgresql://` to SQLAlchemy psycopg3 automatically.

## 2) Push code to a Git repo

Render deploys from Git (GitHub/GitLab).

## 3) Create a Render Web Service

Option A (recommended): **Blueprint**

- Render → New → Blueprint
- Select your repo
- It will read `render.yaml` (repo root)

Option B: Manual Web Service

- Render → New → Web Service
- Runtime: Docker
- Root directory: repo root
- Dockerfile: `backend/Dockerfile`
- Docker context: `backend/`

## 4) Configure environment variables (required)

In Render service settings → Environment:

- `ENVIRONMENT=production`
- `ENABLE_DOCS=false`

### If you can only use Render "Secret Files"

This backend supports Render Secret Files mounted at `/etc/secrets/<NAME>`.

Create Secret Files with these exact names:

- `DATABASE_URL` → your Supabase connection string (include `?sslmode=require`)
- `SECRET_KEY` → strong random secret
- `CORS_ORIGINS` → JSON list, e.g. `["https://<your-frontend-domain>"]`

Then you only need the non-secret env vars:

- `ENVIRONMENT=production`
- `ENABLE_DOCS=false`

Optional:

- `SCHEDULER_ENABLED=false` (recommended unless you run a dedicated worker)

## 5) Run migrations (Alembic)

This backend can run migrations automatically on startup (recommended for single-instance Render services),
or you can run them as a one-off step.

### Recommended (single instance): run migrations on startup

In Render env vars, set:

- `RUN_MIGRATIONS_ON_START=true`

Notes:

- Migrations run inside app startup and use a Postgres advisory lock to avoid concurrent upgrades.
- If you later scale to multiple instances, this is still safe (instances that fail to acquire the lock will skip).

### Alternative: one-off shell / job (safe)

After the first deploy, open a Render shell (or use a one-off job if available) and run:

- `cd backend`
- `alembic upgrade head` (or `python -m alembic upgrade head`)

Why `cd backend`?

- `alembic.ini` lives in `backend/`, so running from that folder avoids path/config mistakes.

Quick verification (optional but useful):

- `alembic current` (shows current revision)
- `alembic heads` (shows repository head)

If you see auth / TLS errors:

- Confirm the Render `DATABASE_URL` matches the Supabase connection string and includes `?sslmode=require`.
- Confirm the username/password are correct for the selected host (direct vs pooler).

### Alternative: run migrations from your machine (same `DATABASE_URL`)

If you prefer to run migrations locally against Supabase:

- Set `DATABASE_URL` in your local `backend/.env` to the Supabase connection string (include `?sslmode=require`).
- From `backend/` run Alembic using the project's Python environment:
	- Windows (recommended): `./.venv311/Scripts/python.exe -m alembic upgrade head`
	- Or activate the venv first, then: `python -m alembic upgrade head`

If you accidentally run with a global/system Python, you may see SQLAlchemy/Alembic import errors due to version incompatibilities.

Safety note:

- Only do this when you are sure your local `DATABASE_URL` is pointing at the intended Supabase project.

### Alternative: run migrations from your machine (same `DATABASE_URL`)

## 6) Point the frontend to Render

Set in the frontend environment:

- `VITE_API_BASE_URL=https://<your-render-service>.onrender.com`

## 7) Stability checklist

- Use Supabase paid plan if you need zero-sleep behavior.
- Keep `--reload` OFF in production.
- Set `CORS_ORIGINS` explicitly (this backend enforces it in production).
- If you scale to multiple instances, ensure scheduler runs in only one place.
