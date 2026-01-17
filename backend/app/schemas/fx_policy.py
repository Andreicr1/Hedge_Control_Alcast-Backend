from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FxPolicyCreate(BaseModel):
    # Canonical key, e.g. "BRL:USDBRL=X@yahoo".
    policy_key: str = Field(..., min_length=3, max_length=128)
    active: bool = True
    notes: Optional[str] = Field(None, max_length=2048)


class FxPolicyRead(BaseModel):
    id: int
    policy_key: str
    reporting_currency: str
    fx_symbol: str
    fx_source: str
    active: bool
    notes: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        orm_mode = True
