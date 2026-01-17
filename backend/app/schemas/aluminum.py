from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AluminumQuoteRead(BaseModel):
    bid: float
    ask: float
    currency: str = "USD"
    unit: str = "ton"
    as_of: datetime
    source: Optional[str] = None


class AluminumHistoryPointRead(BaseModel):
    ts: datetime
    mid: float
    bid: Optional[float] = None
    ask: Optional[float] = None
