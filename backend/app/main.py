# ruff: noqa: I001

import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app import models
from app.api.deps import enforce_auditoria_readonly
from app.api.router import api_router
from app.config import settings
from app.core.observability import (
    global_exception_handler,
    request_logging_middleware,
    uptime_seconds,
    utc_now_iso,
)
from app.database import POOL_CONFIG, SessionLocal, engine
from app.services.auth import hash_password
from app.services.scheduler import runner as daily_runner

api_prefix = (
    settings.api_prefix
    if settings.api_prefix.startswith("/")
    else f"/{settings.api_prefix}"
    if settings.api_prefix
    else ""
)

logger = logging.getLogger("alcast")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url=(f"{api_prefix}/openapi.json" if api_prefix else "/openapi.json")
    if settings.enable_docs
    else None,
    dependencies=[Depends(enforce_auditoria_readonly)],
)

# Expose logger for middleware without creating circular imports.
app.state.logger = logger

# Global exception handler - catches all unhandled exceptions and returns structured error
app.add_exception_handler(Exception, global_exception_handler)

# Request-level logging + request correlation id.
app.middleware("http")(request_logging_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=api_prefix)


def _run_migrations_if_configured() -> None:
    if not bool(getattr(settings, "run_migrations_on_start", False)):
        return

    # Avoid running migrations during tests.
    if (settings.environment or "").lower() == "test":
        return

    # Import lazily to keep import graph light for non-migration startups.
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    backend_root = Path(__file__).resolve().parents[1]
    cfg_path = backend_root / "alembic.ini"
    alembic_cfg = Config(str(cfg_path))

    # Log the DB target (without leaking credentials) so we can diagnose URL parsing
    # issues in container environments.
    try:
        from sqlalchemy.engine.url import make_url

        url_obj = make_url(str(settings.database_url))
        logger.info(
            "migrations_db_target driver=%s host=%s port=%s db=%s user=%s has_password=%s",
            url_obj.drivername,
            url_obj.host,
            url_obj.port,
            url_obj.database,
            url_obj.username,
            bool(url_obj.password),
        )
    except Exception as e:
        logger.warning("migrations_db_target_parse_failed error=%s", str(e))

    try:
        db_engine = create_engine(settings.database_url, future=True)
        with db_engine.connect() as connection:
            dialect = str(connection.dialect.name or "").lower()

            def _to_regclass(qualified: str) -> str | None:
                # Postgres-only. Returns NULL if missing.
                return connection.execute(text("select to_regclass(:q)"), {"q": qualified}).scalar()

            def _bootstrap_alembic_version_if_needed() -> None:
                if dialect != "postgresql":
                    return

                try:
                    alembic_table = _to_regclass("public.alembic_version")
                    if not alembic_table:
                        return

                    count = int(
                        connection.execute(
                            text("select count(*) from public.alembic_version")
                        ).scalar()
                        or 0
                    )
                    if count > 0:
                        return

                    users_table = _to_regclass("public.users")
                    if not users_table:
                        return
                except Exception as e:
                    logger.warning("alembic_bootstrap_check_failed", extra={"error": str(e)})
                    return

                logger.info("alembic_bootstrap_stamp_head")
                command.stamp(alembic_cfg, "head")

            # Best-effort: avoid concurrent migrations across multiple instances.
            lock_acquired = True
            if dialect == "postgresql":
                try:
                    lock_acquired = bool(
                        connection.execute(
                            text("select pg_try_advisory_lock(:k)"), {"k": 91238411}
                        ).scalar()
                    )
                except Exception as e:
                    logger.warning("migrations_lock_failed", extra={"error": str(e)})
                    lock_acquired = True

            if not lock_acquired:
                logger.info("migrations_skipped_lock_not_acquired")
                return

            try:
                # Reuse this connection inside Alembic env.py (config.attributes['connection']).
                alembic_cfg.attributes["connection"] = connection

                # If DB schema exists but alembic_version is empty (legacy bootstrap), stamp head first.
                _bootstrap_alembic_version_if_needed()
                command.upgrade(alembic_cfg, "head")
                logger.info("migrations_applied")
            finally:
                if dialect == "postgresql":
                    try:
                        connection.execute(text("select pg_advisory_unlock(:k)"), {"k": 91238411})
                        connection.commit()
                    except Exception:
                        pass
    except Exception as e:
        # Don't crash the API if migrations fail; surface the issue via logs and
        # let endpoints that require DB return 503.
        logger.error("migrations_failed error=%s", str(e))
        return


def _seed_dev_users() -> None:
    env = str(settings.environment or "dev").lower()
    if env in {"prod", "production", "test"}:
        return

    db = SessionLocal()
    try:
        # Ensure roles exist.
        for role_name in [
            models.RoleName.admin,
            models.RoleName.financeiro,
            models.RoleName.comercial,
            models.RoleName.auditoria,
        ]:
            role = db.query(models.Role).filter(models.Role.name == role_name).first()
            if not role:
                db.add(models.Role(name=role_name, description=str(role_name.value)))

        db.flush()

        def ensure_user(email: str, name: str, role_name: models.RoleName) -> None:
            existing = db.query(models.User).filter(models.User.email == email).first()
            if existing:
                return
            role = db.query(models.Role).filter(models.Role.name == role_name).first()
            if not role:
                return
            db.add(
                models.User(
                    email=email,
                    name=name,
                    hashed_password=hash_password("123"),
                    role_id=role.id,
                    active=True,
                )
            )

        # Default accounts used by the frontend 'Acesso rápido (dev)'.
        ensure_user("admin@alcast.local", "Admin", models.RoleName.admin)
        ensure_user("financeiro@alcast.dev", "Financeiro", models.RoleName.financeiro)
        ensure_user("comercial@alcast.dev", "Comercial", models.RoleName.comercial)
        ensure_user("compras@alcast.dev", "Comercial (alias compras)", models.RoleName.comercial)
        ensure_user("vendas@alcast.dev", "Comercial (alias vendas)", models.RoleName.comercial)
        ensure_user("auditoria@alcast.dev", "Auditoria", models.RoleName.auditoria)

        db.commit()
    except OperationalError as e:
        # Database not ready yet (e.g., missing tables) - don't block startup.
        logger.warning("dev_user_seed_failed", extra={"error": str(e)})
        db.rollback()
    except Exception as e:
        logger.warning("dev_user_seed_failed", extra={"error": str(e)})
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
def _startup_scheduler():
    try:
        pool_status = None
        try:
            pool_status = engine.pool.status()
        except Exception:
            pool_status = None

        logger.info(
            "runtime_config",
            extra={
                "pid": os.getpid(),
                "web_concurrency": os.getenv("WEB_CONCURRENCY"),
                "uvicorn_workers": os.getenv("UVICORN_WORKERS"),
                "db_pool": POOL_CONFIG,
                "db_pool_status": pool_status,
            },
        )
    except Exception:
        pass
    _run_migrations_if_configured()
    _seed_dev_users()
    # Avoid running background threads in test context by default.
    if (settings.environment or "").lower() == "test":
        return
    # Allow ops to disable scheduler via env var if needed.
    if str(getattr(settings, "scheduler_enabled", "true")).lower() in {"0", "false", "no"}:
        return
    daily_runner.start()
    logger.info("scheduler_started", extra={"daily_utc_hour": daily_runner.hour_utc})


@app.on_event("shutdown")
def _shutdown_scheduler():
    try:
        daily_runner.stop()
        logger.info("scheduler_stopped")
    except Exception:
        # don't block shutdown
        pass


@app.get("/", tags=["meta"])
def root():
    docs_path = (
        (f"{api_prefix}/openapi.json" if api_prefix else "/openapi.json")
        if settings.enable_docs
        else None
    )
    logger.info("health_check", extra={"event": "root", "status": "ok"})
    return {"message": "Hedge Control API", "docs": docs_path}


@app.get("/health", tags=["meta"])
@app.get("/healthz", tags=["meta"])
def healthcheck():
    """Institutional healthcheck (liveness).

    Keep payload stable for monitoring systems.
    """

    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "time": utc_now_iso(),
        "uptime_seconds": round(uptime_seconds(), 2),
        "version": getattr(settings, "build_version", None),
    }
