from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services.timeline_emitters import TimelineVisibility, emit_timeline_event


def emit_mtm_contract_snapshot_created(
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
    """Emit the standard MTM snapshot event for the contract-only read model.

    Note: This intentionally reuses the existing event name from the frozen spec
    (MTM_SNAPSHOT_CREATED) while changing the subject_type to make it explicit
    that this is the institutional contract-only read model.
    """

    emit_timeline_event(
        db=db,
        event_type="MTM_SNAPSHOT_CREATED",
        subject_type="mtm_contract_snapshot_run",
        subject_id=int(run_id),
        correlation_id=correlation_id,
        idempotency_key=f"mtm_snapshot:create:{inputs_hash}",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "mtm_contract_snapshot_run_id": int(run_id),
            "inputs_hash": inputs_hash,
            "as_of_date": as_of_date.isoformat(),
            "filters": filters,
            "institutional_layer": "read_model",
        },
        meta=meta,
    )
