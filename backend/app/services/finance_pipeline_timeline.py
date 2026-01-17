from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from app import models
from app.services.audit import audit_event
from app.services.timeline_emitters import (
    EmitResult,
    correlation_id_from_request_id,
    emit_timeline_event,
)

FinancePipelineTimelineEvent = Literal[
    "requested",
    "started",
    "completed",
    "failed",
]


_FINANCE_PIPELINE_EVENT_TYPES: dict[FinancePipelineTimelineEvent, str] = {
    "requested": "FINANCE_PIPELINE_REQUESTED",
    "started": "FINANCE_PIPELINE_STARTED",
    "completed": "FINANCE_PIPELINE_COMPLETED",
    "failed": "FINANCE_PIPELINE_FAILED",
}


def finance_pipeline_idempotency_key(
    *,
    event: FinancePipelineTimelineEvent,
    inputs_hash: str,
) -> str:
    return f"finance_pipeline:{event}:{inputs_hash}"


def emit_finance_pipeline_timeline_event(
    db: Session,
    *,
    event: FinancePipelineTimelineEvent,
    run: models.FinancePipelineRun,
    request_id: str | None,
    actor_user_id: int | None,
    occurred_at: datetime | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> EmitResult:
    """Emit FINANCE_PIPELINE_* Timeline events.

    Constraints:
    - Only emits the frozen set of FINANCE_PIPELINE_* event types.
    - Idempotency uses (event_type, idempotency_key) where:
      idempotency_key = finance_pipeline:{event}:{inputs_hash}
    - Correlation is derived from X-Request-ID (same rule as Timeline routes).
    """

    if event not in _FINANCE_PIPELINE_EVENT_TYPES:
        raise ValueError(f"Invalid finance pipeline timeline event: {event}")

    correlation_id = correlation_id_from_request_id(request_id)
    event_type = _FINANCE_PIPELINE_EVENT_TYPES[event]
    idempotency_key = finance_pipeline_idempotency_key(
        event=event,
        inputs_hash=str(run.inputs_hash),
    )

    payload: dict[str, Any] = {
        "run_id": int(run.id),
        "inputs_hash": str(run.inputs_hash),
        "status": str(run.status),
        "as_of_date": run.as_of_date.isoformat() if run.as_of_date else None,
        "pipeline_version": str(run.pipeline_version),
    }
    if extra_payload:
        payload.update(dict(extra_payload))

    audit_id = audit_event(
        f"finance.pipeline.daily.{event}",
        actor_user_id,
        {
            "event_type": event_type,
            "run_id": int(run.id),
            "inputs_hash": str(run.inputs_hash),
            "correlation_id": correlation_id,
        },
        db=db,
        request_id=request_id,
    )

    return emit_timeline_event(
        db=db,
        event_type=event_type,
        subject_type="finance_pipeline_run",
        subject_id=int(run.id),
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        visibility="finance",
        payload=payload,
        actor_user_id=actor_user_id,
        audit_log_id=audit_id,
        occurred_at=occurred_at,
    )
