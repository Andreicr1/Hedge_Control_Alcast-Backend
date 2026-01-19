from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel


EntityType = Literal["deal", "so", "po", "contract", "exposure"]
CashflowType = Literal["physical", "financial", "risk"]
ValuationMethod = Literal["fixed", "mtm"]
Confidence = Literal["deterministic", "estimated", "risk"]
Direction = Literal["inflow", "outflow"]


class CashFlowLineRead(BaseModel):
    entity_type: EntityType
    entity_id: str
    parent_id: Optional[str] = None

    cashflow_type: CashflowType
    date: date

    # Always a non-negative magnitude; use direction for sign.
    amount: float

    price_type: Optional[str] = None
    valuation_method: ValuationMethod
    valuation_reference_date: Optional[date] = None
    confidence: Confidence
    direction: Direction

    quantity_mt: Optional[float] = None
    unit_price_used: Optional[float] = None

    source_reference: Optional[str] = None
    explanation: Optional[str] = None

    as_of: datetime
