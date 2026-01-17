from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app import models
from app.services.timeline_emitters import TimelineVisibility, emit_timeline_event


def _date_iso(d):
    if d is None:
        return None
    return d.isoformat()


def _fingerprint_exposure(exposure: models.Exposure) -> str:
    payload = {
        "id": int(exposure.id),
        "status": exposure.status.value
        if hasattr(exposure.status, "value")
        else str(exposure.status),
        "quantity_mt": float(exposure.quantity_mt),
        "product": exposure.product,
        "delivery_date": _date_iso(exposure.delivery_date),
        "payment_date": _date_iso(exposure.payment_date),
        "sale_date": _date_iso(exposure.sale_date),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _stable_suffix(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def emit_exposure_created(
    *,
    db: Session,
    exposure: models.Exposure,
    correlation_id: str,
    actor_user_id: int | None,
    visibility: TimelineVisibility = "finance",
) -> None:
    emit_timeline_event(
        db=db,
        event_type="EXPOSURE_CREATED",
        subject_type="exposure",
        subject_id=int(exposure.id),
        correlation_id=correlation_id,
        idempotency_key=f"exposure:{exposure.id}:created",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "exposure_id": int(exposure.id),
            "source_type": exposure.source_type.value,
            "source_id": int(exposure.source_id),
            "exposure_type": exposure.exposure_type.value,
            "quantity_mt": float(exposure.quantity_mt),
            "product": exposure.product,
            "delivery_date": _date_iso(exposure.delivery_date),
        },
    )


def emit_exposure_recalculated(
    *,
    db: Session,
    exposure: models.Exposure,
    correlation_id: str,
    actor_user_id: int | None,
    reason: str,
    visibility: TimelineVisibility = "finance",
) -> None:
    fp = _fingerprint_exposure(exposure)
    emit_timeline_event(
        db=db,
        event_type="EXPOSURE_RECALCULATED",
        subject_type="exposure",
        subject_id=int(exposure.id),
        correlation_id=correlation_id,
        idempotency_key=f"exposure:{exposure.id}:recalculated:{_stable_suffix(fp)}",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "exposure_id": int(exposure.id),
            "status": (
                exposure.status.value if hasattr(exposure.status, "value") else str(exposure.status)
            ),
            "quantity_mt": float(exposure.quantity_mt),
            "product": exposure.product,
            "delivery_date": _date_iso(exposure.delivery_date),
            "reason": reason,
        },
    )


def emit_exposure_closed(
    *,
    db: Session,
    exposure: models.Exposure,
    correlation_id: str,
    actor_user_id: int | None,
    reason: str,
    visibility: TimelineVisibility = "finance",
) -> None:
    emit_timeline_event(
        db=db,
        event_type="EXPOSURE_CLOSED",
        subject_type="exposure",
        subject_id=int(exposure.id),
        correlation_id=correlation_id,
        idempotency_key=f"exposure:{exposure.id}:closed",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "exposure_id": int(exposure.id),
            "status": (
                exposure.status.value if hasattr(exposure.status, "value") else str(exposure.status)
            ),
            "reason": reason,
        },
    )
