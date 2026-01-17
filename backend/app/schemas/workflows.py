from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

WorkflowDecisionValue = Literal["approved", "rejected"]
WorkflowRequestStatus = Literal["pending", "approved", "rejected", "executed"]


class WorkflowDecisionCreate(BaseModel):
    decision: WorkflowDecisionValue
    justification: str = Field(..., min_length=3, max_length=4000)


class WorkflowDecisionRead(BaseModel):
    id: int
    workflow_request_id: int
    decision: WorkflowDecisionValue
    justification: str
    decided_by_user_id: int
    decided_at: datetime
    created_at: datetime

    class Config:
        orm_mode = True


class WorkflowRequestRead(BaseModel):
    id: int
    request_key: str
    inputs_hash: str

    action: str
    subject_type: str
    subject_id: str

    status: WorkflowRequestStatus

    notional_usd: float | None
    threshold_usd: float | None
    required_role: str

    context: dict[str, Any] | None

    requested_by_user_id: int | None
    requested_at: datetime
    sla_due_at: datetime | None

    decided_at: datetime | None
    executed_at: datetime | None
    executed_by_user_id: int | None

    correlation_id: str | None

    created_at: datetime
    updated_at: datetime

    decisions: list[WorkflowDecisionRead] | None = None

    class Config:
        orm_mode = True
