from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.domain import ExposureStatus, ExposureType, HedgeTaskStatus, MarketObjectType


class HedgeTaskRead(BaseModel):
    id: int
    status: HedgeTaskStatus
    created_at: datetime

    class Config:
        orm_mode = True


class ExposureBase(BaseModel):
    source_type: MarketObjectType
    source_id: int
    exposure_type: ExposureType
    quantity_mt: float = Field(..., gt=0)
    product: Optional[str] = Field(None, max_length=255)
    payment_date: Optional[date] = None
    delivery_date: Optional[date] = None
    sale_date: Optional[date] = None
    status: ExposureStatus = ExposureStatus.open


class ExposureRead(ExposureBase):
    class HedgeCoverageRead(BaseModel):
        hedge_id: int
        quantity_mt: float
        counterparty_name: Optional[str] = None
        instrument: Optional[str] = None
        period: Optional[str] = None

        class Config:
            orm_mode = True

    id: int
    created_at: datetime
    tasks: List[HedgeTaskRead] = []

    # Decision/UX fields
    pricing_reference: Optional[str] = None
    hedged_quantity_mt: Optional[float] = None
    unhedged_quantity_mt: Optional[float] = None
    hedges: List[HedgeCoverageRead] = []

    class Config:
        orm_mode = True
