from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RfqAttemptReport(BaseModel):
    rfq_id: int
    attempt_id: int
    channel: str
    status: str
    provider_message_id: Optional[str] = None
    counterparty_name: Optional[str] = None
    created_at: datetime
