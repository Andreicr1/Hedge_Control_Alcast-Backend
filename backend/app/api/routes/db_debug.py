from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/admin/db", tags=["db_debug"])


def _is_prod_env() -> bool:
    env = str(getattr(settings, "environment", "") or "").strip().lower()
    return env in {"prod", "production"}


@router.get(
    "/summary",
    dependencies=[Depends(require_roles(models.RoleName.financeiro))],
    status_code=status.HTTP_200_OK,
)
def db_summary(
    limit: int = Query(default=80, ge=1, le=500),
    include_counts: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Lightweight DB schema/data sanity check.

    Intended for dev/staging only. Returns table list, alembic version (if present),
    and optional row counts (no row contents).
    """

    if _is_prod_env():
        # Avoid leaking any schema info in production.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    bind = db.get_bind()
    dialect = str(getattr(getattr(bind, "dialect", None), "name", ""))

    insp = inspect(bind)
    schema: Optional[str] = "public" if dialect.startswith("postgres") else None

    try:
        tables = insp.get_table_names(schema=schema)
    except TypeError:
        # Some dialects don't accept schema=None.
        tables = insp.get_table_names()

    tables = sorted([t for t in tables if isinstance(t, str)])

    alembic_version = None
    if "alembic_version" in tables:
        try:
            alembic_version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            alembic_version = "<unreadable>"

    row_counts: Dict[str, Optional[int]] = {}
    if include_counts:
        for table_name in tables[:limit]:
            try:
                # Quote identifiers defensively.
                row_counts[table_name] = int(
                    db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
                )
            except Exception:
                row_counts[table_name] = None

    return {
        "dialect": dialect,
        "schema": schema,
        "tables": len(tables),
        "sample_tables": tables[:limit],
        "alembic_version": alembic_version,
        "row_counts": row_counts if include_counts else None,
    }
