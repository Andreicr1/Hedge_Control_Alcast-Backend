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
    id: int
    created_at: datetime
    tasks: List[HedgeTaskRead] = []

    class Config:
        orm_mode = True
