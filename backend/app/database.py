import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

connect_args = {}
# Avoid long hangs on DB outages (psycopg3 supports connect_timeout in seconds).
if str(settings.database_url).startswith("postgresql"):
    connect_args = {"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10"))}

db_url = str(settings.database_url)
is_postgres = db_url.startswith("postgresql")


def _env_bool(key: str, default: str = "false") -> bool:
    v = os.getenv(key, default)
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


engine_kwargs: dict = {"future": True, "connect_args": connect_args}
POOL_CONFIG: dict[str, int | str | None] = {
    "pool_size": None,
    "max_overflow": None,
    "pool_timeout": None,
    "pool_recycle": None,
    "use_null_pool": None,
}

if is_postgres:
    # Keep connections healthy across transient pooler/network glitches.
    engine_kwargs["pool_pre_ping"] = True

    # Defaults tuned for Supabase pooler session mode, where max clients are small.
    is_supabase_pooler = "pooler.supabase.com" in db_url
    default_pool_size = "5" if is_supabase_pooler else "5"
    default_max_overflow = "5" if is_supabase_pooler else "10"

    pool_size = int(os.getenv("DB_POOL_SIZE", default_pool_size))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", default_max_overflow))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))
    pool_recycle = int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800"))

    # For transaction poolers / serverless-style environments, disable pooling.
    if _env_bool("DB_USE_NULL_POOL", "false"):
        engine_kwargs["poolclass"] = NullPool
        POOL_CONFIG.update(
            {
                "pool_size": None,
                "max_overflow": None,
                "pool_timeout": None,
                "pool_recycle": None,
                "use_null_pool": "true",
            }
        )
    else:
        engine_kwargs.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
        )
        POOL_CONFIG.update(
            {
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_timeout": pool_timeout,
                "pool_recycle": pool_recycle,
                "use_null_pool": "false",
            }
        )

engine = create_engine(db_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        if is_postgres:
            timeout_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "5000"))
            if timeout_ms > 0:
                try:
                    db.execute(text(f"SET statement_timeout = {timeout_ms}"))
                except Exception:
                    pass
        yield db
    finally:
        db.close()
