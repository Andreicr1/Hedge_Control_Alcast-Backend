import os
import subprocess
import sys

from sqlalchemy import create_engine, text


def _normalize_database_url(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("postgres://"):
        s = "postgresql://" + s[len("postgres://") :]
    if s.startswith("postgresql+psycopg2://"):
        s = "postgresql+psycopg://" + s[len("postgresql+psycopg2://") :]
    if s.startswith("postgresql://"):
        s = "postgresql+psycopg://" + s[len("postgresql://") :]
    return s


def _to_regclass(conn, qualified: str) -> str | None:
    return conn.execute(text("select to_regclass(:q)"), {"q": qualified}).scalar()


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("[startup] alembic_bootstrap: DATABASE_URL not set", file=sys.stderr)
        return 1

    engine = create_engine(_normalize_database_url(database_url), pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            alembic_table = _to_regclass(conn, "public.alembic_version")
            if not alembic_table:
                print("[startup] alembic_bootstrap: alembic_version table missing; treating as fresh DB")
                return 0

            count = int(conn.execute(text("select count(*) from public.alembic_version")).scalar() or 0)
            if count > 0:
                print("[startup] alembic_bootstrap: alembic_version already set")
                return 0

            users_table = _to_regclass(conn, "public.users")
            if not users_table:
                print(
                    "[startup] alembic_bootstrap: alembic_version empty but users table missing; treating as fresh DB"
                )
                return 0

    except Exception as exc:
        print(f"[startup] alembic_bootstrap: DB check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    # At this point: alembic_version exists but empty, and schema already exists.
    # This happens when schema was created outside Alembic (e.g., SQL bootstrap).
    print("[startup] alembic_bootstrap: existing schema detected with empty alembic_version; stamping head")

    alembic_config = os.environ.get("ALEMBIC_CONFIG", "alembic.ini")
    try:
        subprocess.run(["alembic", "-c", alembic_config, "stamp", "head"], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[startup] alembic_bootstrap: alembic stamp failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
