from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class KycDocumentRead(BaseModel):
    id: int
    owner_type: Literal["customer", "supplier", "counterparty"]
    owner_id: int
    filename: str
    content_type: Optional[str]
    path: str
    uploaded_at: datetime

    class Config:
        orm_mode = True


class CreditCheckRead(BaseModel):
    id: int
    owner_type: Literal["customer", "supplier", "counterparty"]
    owner_id: int
    bureau: Optional[str]
    score: Optional[int]
    status: Optional[str]
    raw_response: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


class KycCheckRead(BaseModel):
    id: int
    owner_type: Literal["customer", "supplier", "counterparty"]
    owner_id: int
    check_type: str
    status: str
    score: Optional[int]
    details_json: Optional[dict]
    created_at: datetime
    expires_at: datetime

    class Config:
        orm_mode = True


class KycPreflightResponse(BaseModel):
    allowed: bool
    reason_code: Optional[str] = None
    blocked_counterparty_id: Optional[int] = None
    missing_items: list[str] = []
    expired_items: list[str] = []
    ttl_info: Optional[dict] = None
