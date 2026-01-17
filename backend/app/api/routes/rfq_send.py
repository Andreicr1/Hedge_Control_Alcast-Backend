# ruff: noqa: B008, E501

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.models.domain import SendStatus
from app.schemas import (
    RfqQuoteSelect,
    RfqRead,
    RfqSendAttemptCreate,
    RfqSendAttemptRead,
    RfqSendAttemptStatusUpdate,
)
from app.services import rfq_sender
from app.services.audit import audit_event
from app.services.rfq_state_timeline import emit_rfq_state_changed
from app.services.rfq_transitions import atomic_transition_rfq_status, coalesce_datetime
from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

router = APIRouter(prefix="/rfqs", tags=["rfq_send"])


@router.post(
    "/{rfq_id}/send",
    response_model=RfqSendAttemptRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(models.RoleName.financeiro))],
)
def send_rfq(
    rfq_id: int,
    payload: RfqSendAttemptCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    from_status = rfq.status
    if not rfq.message_text:
        raise HTTPException(
            status_code=400, detail="RFQ message_text is empty; generate/attach before sending"
        )
    raw_status = rfq.status.value if hasattr(rfq.status, "value") else str(rfq.status)
    status_val = raw_status.split(".")[-1].lower()
    if status_val not in {"draft", "pending", "quoted", "sent"}:
        raise HTTPException(status_code=400, detail=f"RFQ status {status_val} cannot be sent")

    now = datetime.utcnow()

    def _send_single(
        channel: str,
        metadata: dict | None,
        idempotency_key: str | None,
        retry_parent_id: int | None,
    ):
        send_result = rfq_sender.send_rfq_message(
            channel=channel,
            message=rfq.message_text,
            metadata=metadata,
            idempotency_key=idempotency_key,
            max_retries=max(1, payload.max_retries),
        )
        attempt = models.RfqSendAttempt(
            rfq_id=rfq_id,
            channel=channel,
            status=send_result.status,
            provider_message_id=send_result.provider_message_id,
            error=send_result.error,
            metadata_json=json.dumps(metadata or {}),
            idempotency_key=idempotency_key,
            retry_of_attempt_id=retry_parent_id,
            updated_at=now,
        )
        db.add(attempt)
        db.flush()
        return attempt

    attempts: list[models.RfqSendAttempt] = []

    # Atomic guard: only allow transition to `sent` from allowed legacy statuses.
    allowed_from_statuses = {
        models.RfqStatus.draft,
        models.RfqStatus.pending,
        models.RfqStatus.quoted,
        models.RfqStatus.sent,
    }
    transition = atomic_transition_rfq_status(
        db=db,
        rfq_id=rfq_id,
        to_status=models.RfqStatus.sent,
        allowed_from=allowed_from_statuses,
        updates={"sent_at": coalesce_datetime(models.Rfq.sent_at, now)},
        now=now,
    )
    if not transition.updated:
        db.rollback()
        raise HTTPException(status_code=409, detail="RFQ status changed; send not allowed")

    # if channel is "auto", blast to all active counterparties using their preferred channel
    if payload.channel == "auto":
        counterparties = (
            db.query(models.Counterparty).filter(models.Counterparty.active.is_(True)).all()
        )
        if not counterparties:
            raise HTTPException(status_code=400, detail="No active counterparties to send RFQ")
        for cp in counterparties:
            meta = payload.metadata or {}
            if cp.api_headers_json:
                try:
                    meta = {**meta, "headers": json.loads(cp.api_headers_json)}
                except json.JSONDecodeError:
                    meta = payload.metadata or {}
            meta = {**meta, "counterparty_id": cp.id, "counterparty_name": cp.name}
            idempotency_key = f"{payload.idempotency_key or 'auto'}-{cp.id}"
            attempts.append(
                _send_single(
                    cp.preferred_channel, meta, idempotency_key, payload.retry_of_attempt_id
                )
            )
    else:
        idempotency_key = payload.idempotency_key or (payload.metadata or {}).get("idempotency_key")
        retry_parent_id = payload.retry_of_attempt_id
        if idempotency_key and not payload.retry:
            existing_attempt = (
                db.query(models.RfqSendAttempt)
                .filter(
                    models.RfqSendAttempt.rfq_id == rfq_id,
                    models.RfqSendAttempt.idempotency_key == idempotency_key,
                )
                .order_by(models.RfqSendAttempt.created_at.desc())
                .first()
            )
            if existing_attempt:
                audit_event(
                    "rfq.send_idempotent_hit",
                    current_user.id,
                    {
                        "rfq_id": rfq_id,
                        "attempt_id": existing_attempt.id,
                        "idempotency_key": idempotency_key,
                    },
                )
                return existing_attempt
            retry_parent_id = None
        if payload.retry and retry_parent_id is None:
            recent_attempt = (
                db.query(models.RfqSendAttempt)
                .filter(models.RfqSendAttempt.rfq_id == rfq_id)
                .order_by(models.RfqSendAttempt.created_at.desc())
                .first()
            )
            retry_parent_id = recent_attempt.id if recent_attempt else None

        attempts.append(
            _send_single(payload.channel, payload.metadata, idempotency_key, retry_parent_id)
        )

    db.commit()
    for att in attempts:
        db.refresh(att)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    if transition.updated and from_status != models.RfqStatus.sent:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=models.RfqStatus.sent,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
            reason="send",
        )

    emit_timeline_event(
        db=db,
        event_type="RFQ_SEND_REQUESTED",
        subject_type="rfq",
        subject_id=int(rfq.id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq:{rfq.id}:send_requested:{payload.idempotency_key or 'none'}",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "rfq_id": rfq.id,
            "channel": payload.channel,
            "attempt_ids": [a.id for a in attempts],
            "message_length": len(rfq.message_text or ""),
        },
    )

    for a in attempts:
        emit_timeline_event(
            db=db,
            event_type="RFQ_SEND_ATTEMPT_CREATED",
            subject_type="rfq",
            subject_id=int(rfq.id),
            correlation_id=correlation_id,
            idempotency_key=f"rfq_send_attempt:{a.id}:created",
            visibility="finance",
            actor_user_id=getattr(current_user, "id", None),
            payload={
                "rfq_id": rfq.id,
                "attempt_id": a.id,
                "channel": a.channel,
                "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                "provider_message_id": a.provider_message_id,
                "retry_of_attempt_id": a.retry_of_attempt_id,
                "idempotency_key": a.idempotency_key,
            },
        )

    audit_event(
        "rfq.send_requested",
        current_user.id,
        {
            "rfq_id": rfq_id,
            "channel": payload.channel,
            "message_length": len(rfq.message_text or ""),
            "attempts": [a.id for a in attempts],
        },
    )
    return attempts[-1] if attempts else None


@router.post(
    "/{rfq_id}/confirm",
    response_model=RfqRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(models.RoleName.financeiro))],
)
def confirm_rfq_deal(
    rfq_id: int,
    payload: RfqQuoteSelect,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    from_status = rfq.status
    quote = db.get(models.RfqQuote, payload.quote_id)
    if not quote or quote.rfq_id != rfq_id:
        raise HTTPException(status_code=404, detail="Quote not found for RFQ")
    if rfq.status not in (models.RfqStatus.sent, models.RfqStatus.quoted):
        raise HTTPException(
            status_code=400, detail=f"RFQ status {rfq.status.value} cannot be confirmed"
        )

    now = datetime.utcnow()

    transition = atomic_transition_rfq_status(
        db=db,
        rfq_id=rfq_id,
        to_status=models.RfqStatus.awarded,
        allowed_from={models.RfqStatus.sent, models.RfqStatus.quoted},
        updates={"awarded_at": now},
        now=now,
    )
    if not transition.updated:
        db.rollback()
        raise HTTPException(status_code=409, detail="RFQ status changed; confirm not allowed")

    # unselect other quotes for this RFQ
    (
        db.query(models.RfqQuote)
        .filter(models.RfqQuote.rfq_id == rfq_id, models.RfqQuote.id != quote.id)
        .update({models.RfqQuote.selected: False})
    )

    quote.selected = True
    db.add(quote)
    db.commit()
    db.refresh(rfq)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    if transition.updated and from_status != models.RfqStatus.awarded:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=models.RfqStatus.awarded,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
            reason="confirm",
        )
    emit_timeline_event(
        db=db,
        event_type="RFQ_AWARDED",
        subject_type="rfq",
        subject_id=int(rfq.id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq:{rfq.id}:awarded",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "rfq_id": rfq.id,
            "quote_id": quote.id,
            "awarded_at": rfq.awarded_at.isoformat() if getattr(rfq, "awarded_at", None) else None,
            "award_source": "confirm_rfq_deal",
        },
    )

    audit_event(
        "rfq.deal_confirmed",
        current_user.id,
        {"rfq_id": rfq_id, "quote_id": quote.id, "provider": quote.provider},
    )
    return rfq


@router.get(
    "/{rfq_id}/send-attempts",
    response_model=list[RfqSendAttemptRead],
    dependencies=[Depends(require_roles(models.RoleName.financeiro, models.RoleName.auditoria))],
)
def list_send_attempts(rfq_id: int, db: Session = Depends(get_db)):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    return (
        db.query(models.RfqSendAttempt)
        .filter(models.RfqSendAttempt.rfq_id == rfq_id)
        .order_by(models.RfqSendAttempt.created_at.desc())
        .all()
    )


@router.post(
    "/{rfq_id}/send-attempts/{attempt_id}/status",
    response_model=RfqSendAttemptRead,
    dependencies=[Depends(require_roles(models.RoleName.financeiro))],
)
def update_send_attempt_status(
    rfq_id: int,
    attempt_id: int,
    payload: RfqSendAttemptStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    from_status = rfq.status
    attempt = db.get(models.RfqSendAttempt, attempt_id)
    if not attempt or attempt.rfq_id != rfq_id:
        raise HTTPException(status_code=404, detail="Send attempt not found for RFQ")

    attempt.status = payload.status
    if payload.provider_message_id is not None:
        attempt.provider_message_id = payload.provider_message_id
    if payload.error is not None:
        attempt.error = payload.error
    if payload.metadata is not None:
        attempt.metadata_json = json.dumps(payload.metadata)
    if payload.idempotency_key is not None:
        attempt.idempotency_key = payload.idempotency_key

    if payload.status == SendStatus.failed:
        # Atomic guard: do not let a late failure override terminal RFQ statuses.
        transition = atomic_transition_rfq_status(
            db=db,
            rfq_id=rfq_id,
            to_status=models.RfqStatus.failed,
            allowed_from={
                models.RfqStatus.draft,
                models.RfqStatus.pending,
                models.RfqStatus.sent,
                models.RfqStatus.quoted,
            },
        )
    else:
        transition = None

    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    if (
        transition is not None
        and transition.updated
        and from_status != models.RfqStatus.failed
        and payload.status == SendStatus.failed
    ):
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=models.RfqStatus.failed,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
            reason="send_attempt_failed",
        )
    status_key = payload.status.value if hasattr(payload.status, "value") else str(payload.status)
    status_value = attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status)
    emit_timeline_event(
        db=db,
        event_type="RFQ_SEND_ATTEMPT_STATUS_UPDATED",
        subject_type="rfq",
        subject_id=int(rfq.id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq_send_attempt:{attempt.id}:status:{status_key}",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "rfq_id": rfq.id,
            "attempt_id": attempt.id,
            "status": status_value,
            "provider_message_id": attempt.provider_message_id,
            "error": attempt.error,
        },
    )

    audit_event(
        "rfq.send_attempt_updated",
        current_user.id,
        {
            "rfq_id": rfq_id,
            "attempt_id": attempt_id,
            "status": attempt.status.value,
        },
    )
    return attempt
