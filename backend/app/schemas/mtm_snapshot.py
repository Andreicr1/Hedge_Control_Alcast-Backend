from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.domain import MarketObjectType


class MTMSnapshotBase(BaseModel):
    institutional_layer: str = "proxy"
    is_proxy: bool = True

    object_type: MarketObjectType
    object_id: Optional[int] = None
    product: Optional[str] = None
    period: Optional[str] = None
    price: float = Field(..., gt=0)
    quantity_mt: float = Field(..., gt=0)
    mtm_value: float
    as_of_date: date


class MTMSnapshotCreate(BaseModel):
    object_type: MarketObjectType
    object_id: Optional[int] = None
    product: Optional[str] = None
    period: Optional[str] = None
    price: float = Field(..., gt=0)
    as_of_date: Optional[date] = None


class MTMSnapshotRead(MTMSnapshotBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
