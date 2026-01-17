import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import (
    WhatsAppAssociateRequest,
    WhatsAppInboundPayload,
    WhatsAppMessageRead,
    WhatsAppSendRfQRequest,
)
from app.services.rfq_message_builder import build_rfq_message

logger = logging.getLogger("alcast.whatsapp")
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.post("/send-rfq", response_model=List[WhatsAppMessageRead])
def send_rfq_messages(
    payload: WhatsAppSendRfQRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    rfq = db.get(models.Rfq, payload.rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ não encontrada")

    created_messages: List[models.WhatsAppMessage] = []
    for cp_id in payload.counterparty_ids:
        cp = db.get(models.Counterparty, cp_id)
        if not cp:
            continue
        content = build_rfq_message(rfq, cp)
        message = models.WhatsAppMessage(
            rfq_id=rfq.id,
            counterparty_id=cp.id,
            direction=models.WhatsAppDirection.outbound,
            status=models.WhatsAppStatus.queued,
            content_text=content,
            phone=cp.contact_phone,
            raw_payload={"template": payload.template_name, "rfq_number": rfq.rfq_number},
        )
        db.add(message)
        created_messages.append(message)
    db.commit()
    return created_messages


@router.post("/webhook", response_model=WhatsAppMessageRead, status_code=201)
def whatsapp_webhook(
    payload: WhatsAppInboundPayload,
    db: Session = Depends(get_db),
):
    message = models.WhatsAppMessage(
        direction=models.WhatsAppDirection.inbound,
        status=models.WhatsAppStatus.received,
        phone=payload.phone,
        message_id=payload.message_id,
        content_text=payload.content_text,
        raw_payload=payload.raw_payload,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    logger.info(
        "whatsapp.inbound", extra={"message_id": message.message_id, "phone": message.phone}
    )
    return message


@router.get("/messages", response_model=List[WhatsAppMessageRead])
def list_messages(
    rfq_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    query = db.query(models.WhatsAppMessage).order_by(models.WhatsAppMessage.created_at.desc())
    if rfq_id:
        query = query.filter(models.WhatsAppMessage.rfq_id == rfq_id)
    return query.all()


@router.post("/messages/{message_id}/associate", response_model=WhatsAppMessageRead)
def associate_message(
    message_id: int,
    payload: WhatsAppAssociateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    msg = db.get(models.WhatsAppMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada")
    rfq = db.get(models.Rfq, payload.rfq_id)
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ não encontrada")
    msg.rfq_id = payload.rfq_id
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@router.get("/messages/{rfq_id}/export")
def export_messages(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    msgs = (
        db.query(models.WhatsAppMessage)
        .filter(models.WhatsAppMessage.rfq_id == rfq_id)
        .order_by(models.WhatsAppMessage.created_at.asc())
        .all()
    )
    rows = ["id,direction,status,phone,message_id,content_text,created_at"]
    for m in msgs:
        phone = (m.phone or "").replace('"', '""')
        msg_id = (m.message_id or "").replace('"', '""')
        content = (m.content_text or "").replace('"', '""')
        rows.append(
            ",".join(
                [
                    str(m.id),
                    m.direction.value,
                    m.status.value,
                    f'"{phone}"',
                    f'"{msg_id}"',
                    f'"{content}"',
                    m.created_at.isoformat(),
                ]
            )
        )
    csv_data = "\n".join(rows)
    headers = {"Content-Disposition": f'attachment; filename="rfq_{rfq_id}_whatsapp.csv"'}
    return Response(content=csv_data, media_type="text/csv", headers=headers)
