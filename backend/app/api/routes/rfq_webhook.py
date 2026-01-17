# ruff: noqa: B008, E501

import hashlib
import hmac
import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.models.domain import SendStatus
from app.services.audit import audit_event
from app.services.rfq_state_timeline import emit_rfq_state_changed
from app.services.rfq_transitions import atomic_transition_rfq_status
from app.services.timeline_emitters import correlation_id_from_request_id

router = APIRouter(prefix="/rfqs/webhook", tags=["rfq_webhook"])


class WebhookPayload(BaseModel):
    provider_message_id: str
    status: SendStatus
    error: str | None = None
    metadata: dict | None = None


SIGNATURE_HEADER = "x-signature"
TIMESTAMP_HEADER = "x-request-timestamp"
MAX_SKEW_SECONDS = 300


def _valid_signature(
    raw_body: bytes, signature_header: str | None, timestamp_header: str | None
) -> bool:
    if not settings.webhook_secret:
        return True
    if not signature_header:
        return False
    try:
        ts = int(timestamp_header) if timestamp_header else None
    except ValueError:
        ts = None

    if ts is not None:
        now = int(time.time())
        if abs(now - ts) > MAX_SKEW_SECONDS:
            return False

    secret = settings.webhook_secret.encode()
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[-1].strip()
    return hmac.compare_digest(expected, provided)


@router.post("", status_code=status.HTTP_200_OK)
async def update_send_status_webhook(
    payload: WebhookPayload,
    db: Session = Depends(get_db),
    request: Request = None,
    x_api_key: str | None = Header(default=None),
    x_signature: str | None = Header(default=None, convert_underscores=False),
    x_request_timestamp: str | None = Header(default=None, convert_underscores=False),
):
    raw_body = await request.body() if request is not None else b""
    if settings.webhook_secret:
        signature_ok = _valid_signature(raw_body, x_signature, x_request_timestamp)
        api_key_ok = x_api_key == settings.webhook_secret
        if not signature_ok and not api_key_ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
            )
    attempt = (
        db.query(models.RfqSendAttempt)
        .filter(models.RfqSendAttempt.provider_message_id == payload.provider_message_id)
        .first()
    )
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found for provider_message_id")

    rfq = db.get(models.Rfq, attempt.rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    from_status = rfq.status

    attempt.status = payload.status
    attempt.error = payload.error
    attempt.metadata_json = json.dumps(payload.metadata or {})
    attempt.updated_at = datetime.utcnow()

    if payload.status == SendStatus.failed:
        # Atomic guard: do not let a late webhook override terminal RFQ statuses.
        transition = atomic_transition_rfq_status(
            db=db,
            rfq_id=rfq.id,
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

    correlation_id = correlation_id_from_request_id(
        request.headers.get("X-Request-ID") if request is not None else None
    )
    if transition is not None and transition.updated and from_status != models.RfqStatus.failed:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=models.RfqStatus.failed,
            correlation_id=correlation_id,
            actor_user_id=None,
            reason="send_webhook_failed",
        )

    audit_event(
        "rfq.webhook_status",
        None,
        {
            "rfq_id": rfq.id,
            "attempt_id": attempt.id,
            "status": attempt.status.value,
            "signature_valid": True,
        },
    )
    return {"status": attempt.status.value}
