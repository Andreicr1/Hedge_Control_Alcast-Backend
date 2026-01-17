from datetime import date
from typing import Optional

from pydantic import BaseModel


class SettlementItemRead(BaseModel):
    contract_id: Optional[str] = None
    hedge_id: Optional[int] = None
    counterparty_id: Optional[int] = None
    counterparty_name: str
    settlement_date: date
    mtm_today_usd: Optional[float] = None
    settlement_value_usd: Optional[float] = None
