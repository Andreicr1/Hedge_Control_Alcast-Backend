from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class CashflowItemRead(BaseModel):
    contract_id: str
    deal_id: int
    rfq_id: int
    counterparty_id: Optional[int] = None
    settlement_date: Optional[date] = None

    projected_value_usd: Optional[float] = None
    projected_methodology: Optional[str] = None
    projected_as_of: Optional[date] = None

    final_value_usd: Optional[float] = None
    final_methodology: Optional[str] = None

    observation_start: Optional[date] = None
    observation_end_used: Optional[date] = None
    last_published_cash_date: Optional[date] = None

    data_quality_flags: List[str] = Field(default_factory=list)


class CashflowResponseRead(BaseModel):
    as_of: date
    items: List[CashflowItemRead]
