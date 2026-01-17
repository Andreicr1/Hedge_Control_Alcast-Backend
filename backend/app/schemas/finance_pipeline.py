from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

FinancePipelineMode = Literal["materialize", "dry_run"]


class FinancePipelineDailyRunRequest(BaseModel):
    as_of_date: date
    pipeline_version: str = Field(..., min_length=1, max_length=128)
    scope_filters: Optional[dict[str, Any]] = None
    mode: FinancePipelineMode = "materialize"
    emit_exports: bool = True


class FinancePipelineStepStatus(BaseModel):
    step_name: str
    status: str


class FinancePipelineDailyDryRunResponse(BaseModel):
    mode: Literal["dry_run"]
    inputs_hash: str
    as_of_date: date
    pipeline_version: str
    scope_filters: dict[str, Any]
    emit_exports: bool
    ordered_steps: list[str]


class FinancePipelineDailyRunStatusResponse(BaseModel):
    run_id: int
    mode: Literal["materialize"]
    inputs_hash: str
    status: str

    as_of_date: date
    pipeline_version: str
    scope_filters: dict[str, Any]
    emit_exports: bool

    requested_by_user_id: Optional[int] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None

    steps: list[FinancePipelineStepStatus]


FinancePipelineDailyRunResponse = (
    FinancePipelineDailyDryRunResponse | FinancePipelineDailyRunStatusResponse
)
