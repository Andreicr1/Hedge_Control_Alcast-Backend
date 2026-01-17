from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.services.timeline_emitters import TimelineVisibility, emit_timeline_event


def _stable_suffix(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _mtm_record_fingerprint(record: models.MtmRecord) -> dict[str, Any]:
    object_type = (
        record.object_type.value
        if hasattr(record.object_type, "value")
        else str(record.object_type)
    )
    return {
        "as_of_date": record.as_of_date.isoformat() if record.as_of_date else None,
        "object_type": object_type,
        "object_id": int(record.object_id) if record.object_id is not None else None,
        "forward_price": float(record.forward_price) if record.forward_price is not None else None,
        "fx_rate": float(record.fx_rate) if record.fx_rate is not None else None,
        "mtm_value": float(record.mtm_value),
        "methodology": record.methodology,
    }


def _mtm_snapshot_fingerprint(snapshot: models.MTMSnapshot) -> dict[str, Any]:
    object_type = (
        snapshot.object_type.value
        if hasattr(snapshot.object_type, "value")
        else str(snapshot.object_type)
    )
    return {
        "as_of_date": snapshot.as_of_date.isoformat() if snapshot.as_of_date else None,
        "object_type": object_type,
        "object_id": int(snapshot.object_id) if snapshot.object_id is not None else None,
        "product": snapshot.product,
        "period": snapshot.period,
        "price": float(snapshot.price),
    }


def emit_mtm_record_created(
    *,
    db: Session,
    record: models.MtmRecord,
    correlation_id: str,
    actor_user_id: int | None,
    visibility: TimelineVisibility = "finance",
) -> None:
    fp = _mtm_record_fingerprint(record)
    emit_timeline_event(
        db=db,
        event_type="MTM_RECORD_CREATED",
        subject_type="mtm",
        subject_id=int(record.id),
        correlation_id=correlation_id,
        idempotency_key=f"mtm_record:create:{_stable_suffix(fp)}",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "mtm_record_id": int(record.id),
            **fp,
            "institutional_layer": "proxy",
        },
    )


def emit_mtm_snapshot_created(
    *,
    db: Session,
    snapshot: models.MTMSnapshot,
    correlation_id: str,
    actor_user_id: int | None,
    visibility: TimelineVisibility = "finance",
) -> None:
    fp = _mtm_snapshot_fingerprint(snapshot)
    emit_timeline_event(
        db=db,
        event_type="MTM_SNAPSHOT_CREATED",
        subject_type="mtm",
        subject_id=int(snapshot.id),
        correlation_id=correlation_id,
        idempotency_key=f"mtm_snapshot:create:{_stable_suffix(fp)}",
        visibility=visibility,
        actor_user_id=actor_user_id,
        payload={
            "mtm_snapshot_id": int(snapshot.id),
            **fp,
            "quantity_mt": float(snapshot.quantity_mt),
            "mtm_value": float(snapshot.mtm_value),
            "institutional_layer": "proxy",
        },
    )
