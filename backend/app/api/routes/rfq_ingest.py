# ruff: noqa: B008, E501

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.models.domain import RfqStatus
from app.schemas import RfqQuoteCreate, RfqQuoteRead
from app.services.rfq_state_timeline import emit_rfq_state_changed
from app.services.rfq_transitions import atomic_transition_rfq_status
from app.services.timeline_emitters import correlation_id_from_request_id

router = APIRouter(prefix="/rfqs", tags=["rfqs-ingest"])


class RfqIngestRequest(RfqQuoteCreate):
    rfq_id: Optional[int] = None
    channel: Optional[str] = "api"
    message_id: Optional[str] = None


def _is_duplicate(
    db: Session, rfq_id: int, counterparty_id: Optional[int], message_id: Optional[str]
) -> Optional[models.RfqQuote]:
    if not message_id or not counterparty_id:
        return None
    return (
        db.query(models.RfqQuote)
        .filter(
            models.RfqQuote.rfq_id == rfq_id,
            models.RfqQuote.counterparty_id == counterparty_id,
            models.RfqQuote.channel == "whatsapp",
            models.RfqQuote.notes.contains(message_id),
        )
        .first()
    )


@router.post("/{rfq_id}/ingest", response_model=RfqQuoteRead)
def ingest_quote(
    rfq_id: int,
    payload: RfqIngestRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ não encontrado")
    from_status = rfq.status
    if rfq.status == RfqStatus.awarded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ encerrado para novas cotações"
        )

    counterparty_id = payload.counterparty_id
    if not counterparty_id and not payload.counterparty_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Contraparte obrigatória"
        )

    existing = _is_duplicate(db, rfq_id, counterparty_id, payload.message_id)
    if existing:
        return existing

    invitation = None
    if counterparty_id:
        invitation = (
            db.query(models.RfqInvitation)
            .filter(
                models.RfqInvitation.rfq_id == rfq_id,
                models.RfqInvitation.counterparty_id == counterparty_id,
            )
            .first()
        )
    if not invitation and counterparty_id:
        invitation = models.RfqInvitation(
            rfq_id=rfq_id,
            counterparty_id=counterparty_id,
            counterparty_name=payload.counterparty_name,
            status="sent",
        )
        db.add(invitation)

    note_text = payload.notes or ""
    if payload.message_id:
        note_text = f"{note_text} [msg:{payload.message_id}]".strip()

    quote = models.RfqQuote(
        rfq_id=rfq_id,
        counterparty_id=payload.counterparty_id,
        counterparty_name=payload.counterparty_name,
        quote_price=payload.quote_price,
        price_type=payload.price_type,
        volume_mt=payload.volume_mt,
        valid_until=payload.valid_until,
        notes=note_text or None,
        channel=payload.channel or "api",
        status="quoted",
        quoted_at=datetime.utcnow(),
    )
    db.add(quote)

    if invitation:
        invitation.status = "answered"
        invitation.responded_at = quote.quoted_at
        db.add(invitation)

    transition = atomic_transition_rfq_status(
        db=db,
        rfq_id=rfq_id,
        to_status=RfqStatus.quoted,
        allowed_from={RfqStatus.draft, RfqStatus.pending, RfqStatus.sent, RfqStatus.quoted},
    )
    if not transition.updated:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RFQ status changed; ingest not allowed"
        )

    db.commit()
    db.refresh(quote)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    if transition.updated and from_status != RfqStatus.quoted:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq_id),
            from_status=from_status,
            to_status=RfqStatus.quoted,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
            reason="ingest_quote",
        )
    return quote
