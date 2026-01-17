from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExportJobCreate(BaseModel):
    export_type: str = Field("state", min_length=1, max_length=64)
    as_of: Optional[datetime] = None

    subject_type: Optional[str] = Field(None, min_length=1, max_length=32)
    subject_id: Optional[int] = Field(None, ge=1)


class ExportJobRead(BaseModel):
    id: int
    export_id: str
    inputs_hash: str

    export_type: str
    as_of: Optional[datetime] = None
    filters: Optional[dict[str, Any]] = None

    status: str
    requested_by_user_id: Optional[int] = None

    artifacts: Optional[list[dict[str, Any]]] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
