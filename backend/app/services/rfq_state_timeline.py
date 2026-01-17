from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import RfqStatus
from app.services.timeline_emitters import TimelineVisibility, emit_timeline_event


def _status_str(status: Any) -> str:
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def emit_rfq_state_changed(
    *,
    db: Session,
    rfq_id: int,
    from_status: RfqStatus,
    to_status: RfqStatus,
    correlation_id: str,
    actor_user_id: int | None,
    reason: str,
    visibility: TimelineVisibility = "finance",
) -> None:
    from_s = _status_str(from_status)
    to_s = _status_str(to_status)

    emit_timeline_event(
        db=db,
        event_type="RFQ_STATE_CHANGED",
        subject_type="rfq",
        subject_id=int(rfq_id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq:{rfq_id}:state_changed:{from_s}->{to_s}",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "rfq_id": int(rfq_id),
            "from_status": from_s,
            "to_status": to_s,
            "reason": reason,
        },
    )
