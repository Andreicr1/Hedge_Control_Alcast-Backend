from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app import models


class TreasuryDecisionKycGateRead(BaseModel):
    allowed: bool
    reason_code: Optional[str] = None
    details: Optional[dict[str, Any]] = None


class TreasuryDecisionCreate(BaseModel):
    exposure_id: int
    decision_kind: models.TreasuryDecisionKind
    decided_at: Optional[datetime] = None
    notes: Optional[str] = None


class TreasuryKycOverrideCreate(BaseModel):
    reason: str = Field(..., min_length=3)


class TreasuryKycOverrideRead(BaseModel):
    id: int
    decision_id: int
    reason: str
    snapshot_json: Optional[dict[str, Any]] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime


class TreasuryDecisionRead(BaseModel):
    id: int
    exposure_id: int
    decision_kind: models.TreasuryDecisionKind
    decided_at: datetime
    notes: Optional[str] = None
    kyc_gate: Optional[TreasuryDecisionKycGateRead] = None
    # Convenience fields derived from kyc_gate + kyc_override.
    # - ok: gate allowed
    # - needs_override: gate not allowed and no override recorded
    # - overridden: gate not allowed but an override is present
    kyc_state: str
    kyc_requires_override: bool
    created_by_user_id: Optional[int] = None
    created_at: datetime
    kyc_override: Optional[TreasuryKycOverrideRead] = None


class TreasuryDecisionListRead(BaseModel):
    items: list[TreasuryDecisionRead]
