# ruff: noqa: B008, E501, B904

import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db
from app.models.domain import RfqStatus
from app.services.rfq_state_timeline import emit_rfq_state_changed
from app.services.rfq_transitions import atomic_transition_rfq_status
from app.services.timeline_emitters import correlation_id_from_request_id

logger = logging.getLogger("alcast.whatsapp")
router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"])


def _sanitize_number(num: str) -> str:
    return re.sub(r"\D", "", num or "")


def _parse_message(text: str) -> dict:
    rfq_match = re.search(r"RFQ[:\-\s]*([0-9]+)", text, re.IGNORECASE)
    if not rfq_match:
        raise ValueError("RFQ não identificado")
    rfq_id = int(rfq_match.group(1))

    price_match = re.search(r"([0-9]+[.,]?[0-9]*)", text)
    if not price_match:
        raise ValueError("Preço não encontrado")
    price = float(price_match.group(1).replace(",", "."))

    validity_match = re.search(
        r"validade[:\s]*([0-9]{2}[\/\-][0-9]{2}[\/\-][0-9]{2,4}|[0-9]{4}\-[0-9]{2}\-[0-9]{2})",
        text,
        re.IGNORECASE,
    )
    validity_raw = validity_match.group(1) if validity_match else None
    validity_dt = None
    if validity_raw:
        try:
            if "/" in validity_raw:
                day, month, year = validity_raw.replace("-", "/").split("/")
                year = year if len(year) == 4 else f"20{year}"
                validity_dt = datetime.fromisoformat(f"{year}-{month}-{day}T00:00:00")
            else:
                validity_dt = datetime.fromisoformat(f"{validity_raw}T00:00:00")
        except Exception:  # noqa: BLE001
            validity_dt = None

    # remove markers
    observations = re.sub(r"RFQ[:\-\s]*[0-9]+", "", text, flags=re.IGNORECASE)
    observations = re.sub(
        r"validade[:\s]*([0-9]{2}[\/\-][0-9]{2}[\/\-][0-9]{2,4}|[0-9]{4}\-[0-9]{2}\-[0-9]{2})",
        "",
        observations,
        flags=re.IGNORECASE,
    )
    observations = observations.strip()

    return {"rfq_id": rfq_id, "price": price, "validity": validity_dt, "observations": observations}


def _find_counterparty(db: Session, phone: str) -> Optional[models.Counterparty]:
    digits = _sanitize_number(phone)
    if not digits:
        return None
    return (
        db.query(models.Counterparty)
        .filter(models.Counterparty.contact_phone.isnot(None))
        .filter(models.Counterparty.contact_phone.ilike(f"%{digits[-8:]}"))
        .first()
    )


def _verify_signature(signature: Optional[str]) -> bool:
    secret = settings.whatsapp_webhook_secret
    if not secret:
        return True
    return signature == secret


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def whatsapp_webhook(
    request: Request,
    x_provider_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not _verify_signature(x_provider_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Assinatura inválida")

    payload = await request.json()
    logger.info("whatsapp.payload", extra={"payload": payload})
    message_id = payload.get("message_id") or payload.get("id")
    sender = payload.get("from") or payload.get("sender") or ""
    text = payload.get("text") or payload.get("body") or ""

    try:
        parsed = _parse_message(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("whatsapp.parse_failed", extra={"error": str(exc), "message_id": message_id})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mensagem inválida")

    counterparty = _find_counterparty(db, sender)
    if not counterparty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Contraparte não identificada"
        )

    rfq = db.get(models.Rfq, parsed["rfq_id"])
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ não encontrado")
    from_status = rfq.status
    if rfq.status in {RfqStatus.awarded, RfqStatus.failed, RfqStatus.expired}:
        logger.info("whatsapp.ignored_closed", extra={"rfq_id": rfq.id, "message_id": message_id})
        return {"status": "ignored", "reason": "rfq_closed"}

    # Idempotência simples
    existing = None
    if message_id:
        existing = (
            db.query(models.RfqQuote)
            .filter(
                models.RfqQuote.rfq_id == rfq.id,
                models.RfqQuote.counterparty_id == counterparty.id,
                models.RfqQuote.channel == "whatsapp",
                models.RfqQuote.notes.contains(message_id),
            )
            .first()
        )
    if existing:
        return {"status": "ignored", "reason": "duplicate"}

    invitation = (
        db.query(models.RfqInvitation)
        .filter(
            models.RfqInvitation.rfq_id == rfq.id,
            models.RfqInvitation.counterparty_id == counterparty.id,
        )
        .first()
    )
    if not invitation:
        invitation = models.RfqInvitation(
            rfq_id=rfq.id,
            counterparty_id=counterparty.id,
            counterparty_name=counterparty.name,
            status="sent",
        )
        db.add(invitation)

    note_text = parsed["observations"]
    if message_id:
        note_text = f"{note_text} [msg:{message_id}]".strip()

    quote = models.RfqQuote(
        rfq_id=rfq.id,
        counterparty_id=counterparty.id,
        counterparty_name=counterparty.name,
        quote_price=parsed["price"],
        price_type=None,
        volume_mt=None,
        valid_until=parsed["validity"],
        notes=note_text or None,
        channel="whatsapp",
        status="quoted",
        quoted_at=datetime.utcnow(),
    )
    db.add(quote)

    invitation.status = "answered"
    invitation.responded_at = quote.quoted_at
    db.add(invitation)

    transition = atomic_transition_rfq_status(
        db=db,
        rfq_id=rfq.id,
        to_status=RfqStatus.quoted,
        allowed_from={RfqStatus.draft, RfqStatus.pending, RfqStatus.sent, RfqStatus.quoted},
    )
    if not transition.updated:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RFQ status changed; quote not allowed"
        )

    db.commit()

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    if transition.updated and from_status != RfqStatus.quoted:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=RfqStatus.quoted,
            correlation_id=correlation_id,
            actor_user_id=None,
            reason="whatsapp_quote",
        )
    return {"status": "accepted", "rfq_id": rfq.id, "counterparty_id": counterparty.id}
