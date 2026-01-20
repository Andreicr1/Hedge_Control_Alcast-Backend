from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.services import rfq_engine


class OrderInstruction(BaseModel):
    order_type: rfq_engine.OrderType
    validity: Optional[str] = None
    limit_price: Optional[str] = None


class LegInput(BaseModel):
    side: rfq_engine.Side
    price_type: rfq_engine.PriceType
    quantity_mt: float
    month_name: Optional[str] = Field(None, description="Required for AVG")
    year: Optional[int] = Field(None, description="Required for AVG")
    start_date: Optional[date] = Field(None, description="Required for AVGInter")
    end_date: Optional[date] = Field(None, description="Required for AVGInter")
    fixing_date: Optional[date] = Field(None, description="Required for C2R; optional for Fix")
    ppt: Optional[date] = Field(None, description="Override PPT if provided")
    order: Optional[OrderInstruction] = None


class RfqPreviewRequest(BaseModel):
    trade_type: rfq_engine.TradeType
    leg1: LegInput
    leg2: Optional[LegInput] = None
    sync_ppt: bool = False
    language: Literal["en", "pt"] = Field(
        default="en",
        description="Output language. 'en' for brokers, 'pt' for banks (simplified Portuguese).",
    )
    holidays: Optional[List[str]] = Field(
        default=None, description="Optional holiday list in ISO YYYY-MM-DD for business-day calc"
    )
    company_header: Optional[str] = Field(None, description="Prepends 'For <company> Account'")
    company_label_for_payoff: str = Field(default="Alcast")


class RfqPreviewResponse(BaseModel):
    text: str
