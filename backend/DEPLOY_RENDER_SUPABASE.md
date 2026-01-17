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

Example:

- `postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require`

This repo normalizes `postgresql://` to SQLAlchemy psycopg3 automatically.

## 2) Push code to a Git repo

Render deploys from Git (GitHub/GitLab).

## 3) Create a Render Web Service

Option A (recommended): **Blueprint**

- Render → New → Blueprint
- Select your repo
- It will read `backend/render.yaml`

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
- `DATABASE_URL=<supabase-connection-string>`
- `SECRET_KEY=<strong-random>`
- `CORS_ORIGINS=["https://<your-frontend-domain>"]`

Optional:

- `SCHEDULER_ENABLED=false` (recommended unless you run a dedicated worker)

## 5) Run migrations (Alembic)

Because Docker services on Render don’t have a universal “release command” like Fly, use one of these:

### Recommended: one-off shell / job

After the first deploy, open a Render shell (or use a one-off job if available) and run:

- `alembic upgrade head`

### Alternative: temporary start command wrapper

If you prefer automation, you can temporarily change the service start command to:

- `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"`

Then revert after the first deploy.

## 6) Point the frontend to Render

Set in the frontend environment:

- `VITE_API_BASE_URL=https://<your-render-service>.onrender.com`

## 7) Stability checklist

- Use Supabase paid plan if you need zero-sleep behavior.
- Keep `--reload` OFF in production.
- Set `CORS_ORIGINS` explicitly (this backend enforces it in production).
- If you scale to multiple instances, ensure scheduler runs in only one place.
