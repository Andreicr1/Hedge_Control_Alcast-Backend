from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.domain import SendStatus


class RfqSendAttemptCreate(BaseModel):
    channel: str
    status: SendStatus = SendStatus.queued
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None
    idempotency_key: Optional[str] = None
    retry_of_attempt_id: Optional[int] = None
    max_retries: int = 1
    retry: bool = False


class RfqSendAttemptStatusUpdate(BaseModel):
    status: SendStatus
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None
    idempotency_key: Optional[str] = None


class RfqSendAttemptRead(BaseModel):
    id: int
    rfq_id: int
    channel: str
    status: SendStatus
    provider_message_id: Optional[str]
    error: Optional[str]
    idempotency_key: Optional[str]
    retry_of_attempt_id: Optional[int]
    metadata: Optional[dict] = Field(default=None, alias="metadata_dict")
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
