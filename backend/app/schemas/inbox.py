from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.exposures import ExposureRead


class InboxCounts(BaseModel):
    purchase_orders_pending: int = 0
    sales_orders_pending: int = 0
    rfqs_draft: int = 0
    rfqs_sent: int = 0
    exposures_active: int = 0
    exposures_passive: int = 0
    exposures_residual: int = 0


class InboxNetExposureRow(BaseModel):
    product: str
    period: str
    gross_active: float
    gross_passive: float
    hedged: float
    net: float


class InboxWorkbenchResponse(BaseModel):
    counts: InboxCounts
    net_exposure: List[InboxNetExposureRow]
    active: List[ExposureRead]
    passive: List[ExposureRead]
    residual: List[ExposureRead]


InboxDecisionType = Literal["no_hedge"]


class InboxDecisionCreate(BaseModel):
    decision: InboxDecisionType = Field(
        ..., description="Decision type (only 'no_hedge' supported in Sprint 2)"
    )
    justification: str = Field(..., min_length=3, max_length=4000)


class InboxDecisionRead(BaseModel):
    id: int
    decision: InboxDecisionType
    justification: str
    created_at: datetime
    created_by_user_id: Optional[int] = None
