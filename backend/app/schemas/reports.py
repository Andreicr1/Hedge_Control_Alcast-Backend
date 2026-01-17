from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RfqReportItem(BaseModel):
    rfq_id: int
    quote_id: int
    provider: str
    price: float
    fee_bps: Optional[float] = None
    currency: str
    created_at: datetime
    selected: bool


class RfqExportItem(BaseModel):
    rfq_id: int
    rfq_status: str
    rfq_channel: str
    rfq_created_at: datetime
    provider: Optional[str] = None
    attempt_status: Optional[str] = None
    attempt_channel: Optional[str] = None
    attempt_created_at: Optional[datetime] = None
    quote_id: Optional[int] = None
    quote_price: Optional[float] = None
    quote_fee_bps: Optional[float] = None
    quote_currency: Optional[str] = None
    quote_selected: Optional[bool] = None
