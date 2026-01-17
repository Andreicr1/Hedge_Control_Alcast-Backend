from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.timeline_emitters import TimelineVisibility, emit_timeline_event


def emit_pnl_snapshot_created(
    *,
    db: Session,
    run_id: int,
    inputs_hash: str,
    as_of_date: date,
    filters: dict[str, Any],
    correlation_id: str,
    actor_user_id: int | None,
    visibility: TimelineVisibility = "finance",
    meta: Optional[dict[str, Any]] = None,
) -> None:
    emit_timeline_event(
        db=db,
        event_type="PNL_SNAPSHOT_CREATED",
        subject_type="pnl_snapshot_run",
        subject_id=int(run_id),
        correlation_id=correlation_id,
        idempotency_key=f"pnl_snapshot:create:{inputs_hash}",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "pnl_snapshot_run_id": int(run_id),
            "inputs_hash": inputs_hash,
            "as_of_date": as_of_date.isoformat(),
            "filters": filters,
            "institutional_layer": "read_model",
        },
        meta=meta,
    )
