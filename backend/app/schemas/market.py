from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.domain import MarketObjectType


class MarketPriceBase(BaseModel):
    source: str
    symbol: str
    contract_month: Optional[str]
    price: float
    currency: str = "USD"
    as_of: datetime
    fx: Optional[bool] = Field(default=False, description="Flag for FX rates (e.g., USD/BRL)")


class MarketPriceCreate(MarketPriceBase):
    pass


class MarketPriceRead(MarketPriceBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class MtmRecordBase(BaseModel):
    institutional_layer: str = "proxy"
    is_proxy: bool = True

    as_of_date: date
    object_type: MarketObjectType
    object_id: Optional[int]
    forward_price: Optional[float]
    fx_rate: Optional[float]
    mtm_value: float
    methodology: Optional[str]


class MtmRecordCreate(MtmRecordBase):
    pass


class MtmRecordRead(MtmRecordBase):
    id: int
    computed_at: datetime

    class Config:
        orm_mode = True
