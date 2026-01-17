# Deploy: Supabase (Postgres) + Fly.io (FastAPI)

This is the recommended “stable remote” setup for this repo:

- **DB:** Supabase Postgres
- **API:** Fly.io (Docker)

## 1) Create the Supabase Postgres

1. Create a Supabase project.
2. Get the Postgres connection string.

### Connection string format

Supabase typically gives a `postgresql://...` URL. This backend supports that and will normalize it to SQLAlchemy’s psycopg3 driver automatically.

**Make sure TLS is enabled** (recommended): append `?sslmode=require`.

Example:

- `postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require`

## 2) Create the Fly.io app

From `backend/`:

- `fly launch --no-deploy`

This will create/update `fly.toml`.

## 3) Configure secrets (required)

From `backend/`:

- `fly secrets set DATABASE_URL="postgresql://...?..."`
- `fly secrets set SECRET_KEY="<strong-random>"`
- `fly secrets set CORS_ORIGINS='["https://<your-frontend-domain>"]'`

Optional but useful:

- `fly secrets set WEBHOOK_SECRET="..."`
- `fly secrets set WHATSAPP_WEBHOOK_SECRET="..."`

## 4) Deploy

- `fly deploy`

Notes:

- Migrations run automatically via Fly `release_command` (`alembic upgrade head`).
- Healthcheck is `GET /health`.

## 5) Frontend

Point the frontend to the Fly API URL:

- `VITE_API_BASE_URL=https://<your-fly-app>.fly.dev`

## 6) Common pitfalls

- **CORS in production:** this backend requires `CORS_ORIGINS` explicitly when `ENVIRONMENT=production`.
- **Scheduler:** in production, consider running scheduler in a single worker instead of every web replica. `fly.toml` defaults to `SCHEDULER_ENABLED=false`.
- **Supabase free tier:** can sleep/slow down; for “always available” prefer a paid plan.
