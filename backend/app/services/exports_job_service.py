from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.exports_manifest import compute_export_id_and_hash


def ensure_export_job(
    db: Session,
    *,
    export_type: str,
    as_of: datetime | None,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
) -> tuple[models.ExportJob, bool]:
    """Ensure an ExportJob exists for the given deterministic export inputs.

    Returns (job, idempotent) where idempotent=True means an existing job was reused.

    Important: this function is safe to call inside larger transactions; it uses a
    SAVEPOINT to handle unique conflicts without rolling back the caller's work.
    """

    export_id, inputs_hash = compute_export_id_and_hash(
        export_type=str(export_type),
        as_of=as_of,
        filters=dict(filters or {}),
    )

    existing = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
    if existing is not None:
        return existing, True

    job = models.ExportJob(
        export_id=export_id,
        inputs_hash=inputs_hash,
        export_type=str(export_type),
        as_of=as_of,
        filters=dict(filters or {}),
        status="queued",
        requested_by_user_id=requested_by_user_id,
    )

    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        # Another concurrent transaction inserted the same deterministic export_id.
        existing = (
            db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
        )
        if existing is None:
            raise
        return existing, True

    return job, False
