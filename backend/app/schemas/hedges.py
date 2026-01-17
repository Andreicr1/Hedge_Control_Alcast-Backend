from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.domain import HedgeStatus


class HedgeBase(BaseModel):
    deal_id: int
    so_id: int
    counterparty_id: int
    quantity_mt: float
    contract_price: float
    current_market_price: Optional[float] = None
    mtm_value: Optional[float] = None
    period: str
    maturity_date: Optional[date] = None
    status: HedgeStatus = HedgeStatus.active


class HedgeCreate(HedgeBase):
    pass


class HedgeUpdate(BaseModel):
    deal_id: Optional[int] = None
    so_id: Optional[int] = None
    counterparty_id: Optional[int] = None
    quantity_mt: Optional[float] = None
    contract_price: Optional[float] = None
    current_market_price: Optional[float] = None
    mtm_value: Optional[float] = None
    period: Optional[str] = None
    maturity_date: Optional[date] = None
    status: Optional[HedgeStatus] = None


class HedgeRead(HedgeBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
