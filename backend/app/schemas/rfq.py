from typing import Optional

from pydantic import BaseModel


class RfqQuoteSelect(BaseModel):
    quote_id: int


class RfqAwardRequest(BaseModel):
    quote_id: int
    motivo: Optional[str] = None
    hedge_id: Optional[int] = None
    hedge_reference: Optional[str] = None
    workflow_request_id: Optional[int] = None
