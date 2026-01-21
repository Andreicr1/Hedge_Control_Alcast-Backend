# ruff: noqa: I001

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel


LedgerEntityType = Literal["so", "po", "contract_leg"]
LedgerCategory = Literal["physical", "financial"]
LedgerDirection = Literal["inflow", "outflow"]
LegSide = Literal["buy", "sell"]


class CashflowLedgerLineRead(BaseModel):
    valuation_as_of_date: date
    valuation_reference_date: date
    as_of: datetime

    deal_id: Optional[int] = None
    deal_uuid: Optional[str] = None

    entity_type: LedgerEntityType
    entity_id: str
    source_reference: Optional[str] = None

    category: LedgerCategory
    date: date

    side: Optional[LegSide] = None
    price_type: Optional[str] = None

    quantity_mt: Optional[float] = None
    unit_price_used: Optional[float] = None
    premium_usd_per_mt: Optional[float] = None

    amount_usd: float
    amount_usd_abs: float
    direction: LedgerDirection

    lme_symbol_used: Optional[str] = None
    lme_price_type: Optional[str] = None
    lme_price_ts_date: Optional[date] = None

    notes: Optional[str] = None
