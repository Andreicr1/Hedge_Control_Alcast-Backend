from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

TimelineVisibility = Literal["all", "finance"]


def correlation_id_from_request_id(request_id: str | None) -> str:
    """Resolve correlation_id for Timeline emissions.

    Rules (per frozen Phase 2 ticket pack):
    - If X-Request-ID is a valid UUID, reuse it.
    - Else generate a UUID4.
    """

    if request_id:
        try:
            return str(uuid.UUID(str(request_id)))
        except ValueError:
            pass
    return str(uuid.uuid4())


@dataclass(frozen=True)
class EmitResult:
    event: models.TimelineEvent
    created: bool


def emit_timeline_event(
    *,
    db: Session,
    event_type: str,
    subject_type: str,
    subject_id: int,
    correlation_id: str,
    idempotency_key: str,
    visibility: TimelineVisibility = "finance",
    payload: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
    audit_log_id: int | None = None,
    occurred_at: datetime | None = None,
    supersedes_event_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> EmitResult:
    """Insert a TimelineEvent with deterministic idempotency.

    - Uses the existing unique constraint on (event_type, idempotency_key)
    - On idempotency conflict, returns the existing event.
    """

    ev = models.TimelineEvent(
        event_type=event_type,
        occurred_at=occurred_at or datetime.utcnow(),
        subject_type=subject_type,
        subject_id=int(subject_id),
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        supersedes_event_id=supersedes_event_id,
        visibility=visibility,
        payload=payload or None,
        meta=meta or None,
        actor_user_id=actor_user_id,
        audit_log_id=audit_log_id,
    )

    db.add(ev)
    try:
        db.commit()
        db.refresh(ev)
        return EmitResult(event=ev, created=True)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == event_type)
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .order_by(models.TimelineEvent.id.desc())
            .first()
        )
        if existing is None:
            raise
        return EmitResult(event=existing, created=False)
