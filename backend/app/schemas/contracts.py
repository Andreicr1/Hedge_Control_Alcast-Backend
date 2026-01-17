from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.models.domain import ExposureStatus, ExposureType, MarketObjectType


class ContractRead(BaseModel):
    contract_id: str
    contract_number: Optional[str] = None
    deal_id: int
    rfq_id: int
    counterparty_id: Optional[int] = None
    status: str
    trade_index: Optional[int] = None
    quote_group_id: Optional[str] = None
    trade_snapshot: dict
    settlement_date: Optional[date] = None
    settlement_meta: Optional[dict[str, Any]] = None
    created_at: datetime

    class Config:
        orm_mode = True


class ContractCounterpartyMiniRead(BaseModel):
    id: int
    name: str


class ContractLegRead(BaseModel):
    side: str
    quantity_mt: float
    price_type: Optional[str] = None
    price: Optional[float] = None
    valid_until: Optional[datetime] = None
    notes: Optional[str] = None

    # Enriched from RFQ trade_specs when available
    month_name: Optional[str] = None
    year: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    fixing_date: Optional[date] = None


class ContractDetailRead(BaseModel):
    contract_id: str
    contract_number: Optional[str] = None
    deal_id: int
    rfq_id: int

    counterparty_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    counterparty: Optional[ContractCounterpartyMiniRead] = None

    status: str
    trade_index: Optional[int] = None
    quote_group_id: Optional[str] = None

    # Raw snapshot kept for audit/debug
    trade_snapshot: dict

    # Parsed legs
    legs: list[ContractLegRead]
    fixed_leg: Optional[ContractLegRead] = None
    variable_leg: Optional[ContractLegRead] = None
    fixed_price: Optional[float] = None
    variable_reference_type: Optional[str] = None  # avg | avg_inter | c2r | unknown
    variable_reference_label: Optional[str] = None
    observation_start: Optional[date] = None
    observation_end: Optional[date] = None

    # Dates
    maturity_date: Optional[date] = None
    settlement_date: Optional[date] = None
    settlement_meta: Optional[dict[str, Any]] = None

    # Post-maturity (vencido/settled) view
    post_maturity_status: str  # active | vencido | settled | cancelled
    settlement_adjustment_usd: Optional[float] = None
    settlement_adjustment_methodology: Optional[str] = None
    settlement_adjustment_locked: bool = False

    created_at: datetime


class ContractExposureLinkRead(BaseModel):
    exposure_id: int
    quantity_mt: float

    source_type: MarketObjectType
    source_id: int
    exposure_type: ExposureType
    status: ExposureStatus

    class Config:
        orm_mode = True
