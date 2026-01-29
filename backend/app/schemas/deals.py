from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.domain import DealCommercialStatus, DealLifecycleStatus, DealStatus


class DealRead(BaseModel):
    id: int
    deal_uuid: str
    reference_name: Optional[str] = None
    commodity: Optional[str]
    company: Optional[str] = None
    economic_period: Optional[str] = None
    commercial_status: DealCommercialStatus
    currency: str
    status: DealStatus
    lifecycle_status: DealLifecycleStatus
    created_at: datetime

    class Config:
        orm_mode = True


class DealUpdate(BaseModel):
    reference_name: Optional[str] = None
    company: Optional[str] = None
    economic_period: Optional[str] = None
    commercial_status: Optional[DealCommercialStatus] = None


class DealCreate(BaseModel):
    reference_name: Optional[str] = None
    commodity: Optional[str] = None
    company: Optional[str] = None
    economic_period: Optional[str] = None
    commercial_status: Optional[DealCommercialStatus] = None
    currency: Optional[str] = None


class PhysicalLeg(BaseModel):
    source: str
    source_id: int
    direction: str
    quantity_mt: float
    pricing_type: Optional[str] = None
    pricing_reference: Optional[str] = None
    fixed_price: Optional[float] = None
    status: Optional[str] = None


class HedgeLeg(BaseModel):
    hedge_id: int
    direction: str
    quantity_mt: float
    contract_period: Optional[str] = None
    entry_price: float
    mtm_price: float
    mtm_value: float
    status: str


class DealPnlResponse(BaseModel):
    deal_id: int
    status: DealStatus
    commodity: Optional[str]
    currency: str
    physical_revenue: float
    physical_cost: float
    hedge_pnl_realized: float
    hedge_pnl_mtm: float
    net_pnl: float
    snapshot_at: datetime
    physical_legs: List[PhysicalLeg]
    hedge_legs: List[HedgeLeg]

    class Config:
        orm_mode = True
