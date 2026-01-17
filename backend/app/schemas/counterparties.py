from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.domain import CounterpartyType


class CounterpartyBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    type: CounterpartyType
    rfq_channel_type: Optional[str] = Field("BROKER_LME", max_length=32)
    trade_name: Optional[str] = Field(None, max_length=255)
    legal_name: Optional[str] = Field(None, max_length=255)
    entity_type: Optional[str] = Field(None, max_length=64)
    contact_name: Optional[str] = Field(None, max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(None, max_length=64)
    address_line: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=128)
    state: Optional[str] = Field(None, max_length=64)
    country: Optional[str] = Field(None, max_length=64)
    postal_code: Optional[str] = Field(None, max_length=32)
    country_incorporation: Optional[str] = Field(None, max_length=64)
    country_operation: Optional[str] = Field(None, max_length=64)
    tax_id: Optional[str] = Field(None, max_length=64)
    tax_id_type: Optional[str] = Field(None, max_length=32)
    tax_id_country: Optional[str] = Field(None, max_length=32)
    base_currency: Optional[str] = Field(None, max_length=8)
    payment_terms: Optional[str] = Field(None, max_length=128)
    risk_rating: Optional[str] = Field(None, max_length=64)
    sanctions_flag: Optional[bool] = None
    kyc_status: Optional[str] = Field(None, max_length=32)
    kyc_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    active: bool = True


class CounterpartyCreate(CounterpartyBase):
    pass


class CounterpartyUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[CounterpartyType] = None
    trade_name: Optional[str] = None
    legal_name: Optional[str] = None
    entity_type: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    country_incorporation: Optional[str] = None
    country_operation: Optional[str] = None
    tax_id: Optional[str] = None
    tax_id_type: Optional[str] = None
    tax_id_country: Optional[str] = None
    base_currency: Optional[str] = None
    payment_terms: Optional[str] = None
    risk_rating: Optional[str] = None
    sanctions_flag: Optional[bool] = None
    kyc_status: Optional[str] = None
    kyc_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    active: Optional[bool] = None


class CounterpartyRead(CounterpartyBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True
