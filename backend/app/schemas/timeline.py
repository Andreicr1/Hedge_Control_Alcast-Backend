from __future__ import annotations

# ruff: noqa: I001

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


TimelineVisibility = Literal["all", "finance"]


class TimelineEventRead(BaseModel):
    id: int
    event_type: str
    occurred_at: datetime
    created_at: datetime

    subject_type: str
    subject_id: int

    correlation_id: str
    supersedes_event_id: Optional[int] = None

    idempotency_key: Optional[str] = None
    actor_user_id: Optional[int] = None
    audit_log_id: Optional[int] = None

    visibility: TimelineVisibility

    payload: Optional[dict] = None
    meta: Optional[dict] = None

    class Config:
        orm_mode = True


class TimelineEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)

    subject_type: str = Field(..., min_length=1, max_length=32)
    subject_id: int

    occurred_at: Optional[datetime] = None

    correlation_id: Optional[str] = None
    supersedes_event_id: Optional[int] = None

    idempotency_key: Optional[str] = Field(None, max_length=128)

    visibility: TimelineVisibility = "all"

    payload: Optional[dict] = None
    meta: Optional[dict] = None


class TimelineHumanCommentCreate(BaseModel):
    subject_type: str = Field(..., min_length=1, max_length=32)
    subject_id: int = Field(..., ge=1)

    body: str = Field(..., min_length=1, max_length=10_000)

    idempotency_key: Optional[str] = Field(None, max_length=128)
    visibility: TimelineVisibility = "all"

    mentions: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)

    meta: Optional[dict] = None


class TimelineHumanCommentCorrectionCreate(BaseModel):
    supersedes_event_id: int = Field(..., ge=1)

    body: str = Field(..., min_length=1, max_length=10_000)

    idempotency_key: Optional[str] = Field(None, max_length=128)

    mentions: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)

    meta: Optional[dict] = None


class TimelineHumanAttachmentCreate(BaseModel):
    subject_type: str = Field(..., min_length=1, max_length=32)
    subject_id: int = Field(..., ge=1)

    file_id: str = Field(..., min_length=1, max_length=128)
    file_name: str = Field(..., min_length=1, max_length=255)
    mime: str = Field(..., min_length=1, max_length=255)
    size: int = Field(..., ge=0)
    checksum: Optional[str] = Field(None, max_length=255)
    storage_uri: str = Field(..., min_length=1, max_length=2_048)

    idempotency_key: Optional[str] = Field(None, max_length=128)
    visibility: TimelineVisibility = "all"

    meta: Optional[dict] = None


class TimelineHumanAttachmentUploadRead(BaseModel):
    file_id: str
    file_name: str
    mime: str
    size: int
    checksum: str
    storage_uri: str
