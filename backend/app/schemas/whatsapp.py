from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.domain import WhatsAppDirection, WhatsAppStatus


class WhatsAppMessageBase(BaseModel):
    rfq_id: Optional[int] = None
    counterparty_id: Optional[int] = None
    phone: Optional[str] = Field(None, max_length=32)
    content_text: Optional[str] = None


class WhatsAppMessageCreate(WhatsAppMessageBase):
    direction: WhatsAppDirection
    status: WhatsAppStatus = WhatsAppStatus.queued
    message_id: Optional[str] = None
    raw_payload: Optional[dict] = None


class WhatsAppInboundPayload(BaseModel):
    phone: Optional[str] = None
    message_id: Optional[str] = None
    content_text: str
    raw_payload: dict


class WhatsAppMessageRead(WhatsAppMessageBase):
    id: int
    direction: WhatsAppDirection
    status: WhatsAppStatus
    message_id: Optional[str] = None
    raw_payload: Optional[dict] = None
    created_at: datetime

    class Config:
        orm_mode = True


class WhatsAppSendRfQRequest(BaseModel):
    rfq_id: int
    counterparty_ids: list[int]
    template_name: str


class WhatsAppAssociateRequest(BaseModel):
    rfq_id: int
