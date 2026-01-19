from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, validator

from app.models.domain import OrderStatus, PriceType


class SupplierBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: Optional[str] = Field(None, max_length=32)
    trade_name: Optional[str] = Field(None, max_length=255)
    entity_type: Optional[str] = Field(None, max_length=64)
    legal_name: Optional[str] = None
    tax_id: Optional[str] = Field(None, max_length=32)
    tax_id_type: Optional[str] = Field(None, max_length=32)
    tax_id_country: Optional[str] = Field(None, max_length=32)
    state_registration: Optional[str] = Field(None, max_length=64)
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=8)
    country: Optional[str] = Field(None, max_length=64)
    postal_code: Optional[str] = Field(None, max_length=32)
    country_incorporation: Optional[str] = Field(None, max_length=64)
    country_operation: Optional[str] = Field(None, max_length=64)
    country_residence: Optional[str] = Field(None, max_length=64)
    credit_limit: Optional[float] = Field(None, ge=0)
    credit_score: Optional[int] = Field(None, ge=0, le=1000)
    kyc_status: Optional[str] = None
    kyc_notes: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    base_currency: Optional[str] = Field(None, max_length=8)
    payment_terms: Optional[str] = Field(None, max_length=128)
    risk_rating: Optional[str] = Field(None, max_length=64)
    sanctions_flag: Optional[bool] = None
    internal_notes: Optional[str] = None
    active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    trade_name: Optional[str] = None
    entity_type: Optional[str] = None
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    tax_id_type: Optional[str] = None
    tax_id_country: Optional[str] = None
    state_registration: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    country_incorporation: Optional[str] = None
    country_operation: Optional[str] = None
    country_residence: Optional[str] = None
    credit_limit: Optional[float] = None
    credit_score: Optional[int] = None
    kyc_status: Optional[str] = None
    kyc_notes: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    base_currency: Optional[str] = None
    payment_terms: Optional[str] = None
    risk_rating: Optional[str] = None
    sanctions_flag: Optional[bool] = None
    internal_notes: Optional[str] = None
    active: Optional[bool] = None


class SupplierRead(SupplierBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class CustomerBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: Optional[str] = Field(None, max_length=32)
    trade_name: Optional[str] = Field(None, max_length=255)
    legal_name: Optional[str] = None
    entity_type: Optional[str] = Field(None, max_length=64)
    tax_id: Optional[str] = Field(None, max_length=32)
    tax_id_type: Optional[str] = Field(None, max_length=32)
    tax_id_country: Optional[str] = Field(None, max_length=32)
    state_registration: Optional[str] = Field(None, max_length=64)
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=8)
    country: Optional[str] = Field(None, max_length=64)
    postal_code: Optional[str] = Field(None, max_length=32)
    country_incorporation: Optional[str] = Field(None, max_length=64)
    country_operation: Optional[str] = Field(None, max_length=64)
    country_residence: Optional[str] = Field(None, max_length=64)
    credit_limit: Optional[float] = Field(None, ge=0)
    credit_score: Optional[int] = Field(None, ge=0, le=1000)
    kyc_status: Optional[str] = None
    kyc_notes: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    base_currency: Optional[str] = Field(None, max_length=8)
    payment_terms: Optional[str] = Field(None, max_length=128)
    risk_rating: Optional[str] = Field(None, max_length=64)
    sanctions_flag: Optional[bool] = None
    internal_notes: Optional[str] = None
    active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    trade_name: Optional[str] = None
    legal_name: Optional[str] = None
    entity_type: Optional[str] = None
    tax_id: Optional[str] = None
    tax_id_type: Optional[str] = None
    tax_id_country: Optional[str] = None
    state_registration: Optional[str] = None
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    country_incorporation: Optional[str] = None
    country_operation: Optional[str] = None
    country_residence: Optional[str] = None
    credit_limit: Optional[float] = None
    credit_score: Optional[int] = None
    kyc_status: Optional[str] = None
    kyc_notes: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    base_currency: Optional[str] = None
    payment_terms: Optional[str] = None
    risk_rating: Optional[str] = None
    sanctions_flag: Optional[bool] = None
    internal_notes: Optional[str] = None
    active: Optional[bool] = None


class CustomerRead(CustomerBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class PurchaseOrderBase(BaseModel):
    po_number: Optional[str] = None
    supplier_id: int
    deal_id: Optional[int] = None
    product: Optional[str] = Field(None, max_length=255)
    total_quantity_mt: float = Field(..., gt=0)
    unit: Optional[str] = Field("MT", max_length=16)
    unit_price: Optional[float] = Field(None, ge=0)
    pricing_type: PriceType
    pricing_period: Optional[str] = Field(None, max_length=32)
    lme_premium: float = Field(0.0, ge=0)
    premium: Optional[float] = Field(None, ge=0)
    reference_price: Optional[str] = Field(None, max_length=64)
    fixing_deadline: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    location: Optional[str] = Field(None, max_length=128)
    avg_cost: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=5000)
    status: OrderStatus = OrderStatus.draft


class PurchaseOrderCreate(PurchaseOrderBase):
    pass


class PurchaseOrderUpdate(BaseModel):
    po_number: Optional[str] = None
    supplier_id: Optional[int] = None
    deal_id: Optional[int] = None
    product: Optional[str] = None
    total_quantity_mt: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    pricing_type: Optional[PriceType] = None
    pricing_period: Optional[str] = None
    lme_premium: Optional[float] = None
    premium: Optional[float] = None
    reference_price: Optional[str] = None
    fixing_deadline: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    location: Optional[str] = None
    avg_cost: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[OrderStatus] = None


class PurchaseOrderRead(PurchaseOrderBase):
    id: int
    created_at: datetime
    supplier: Optional[SupplierRead]

    class Config:
        orm_mode = True


class SalesOrderBase(BaseModel):
    so_number: Optional[str] = None
    deal_id: Optional[int] = None
    customer_id: int
    product: Optional[str] = Field(None, max_length=255)
    total_quantity_mt: float = Field(..., gt=0)
    unit: Optional[str] = Field("MT", max_length=16)
    unit_price: Optional[float] = Field(None, ge=0)
    pricing_type: PriceType
    pricing_period: Optional[str] = Field(None, max_length=32)
    lme_premium: float = Field(0.0, ge=0)
    premium: Optional[float] = Field(None, ge=0)
    reference_price: Optional[str] = Field(None, max_length=64)
    fixing_deadline: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    location: Optional[str] = Field(None, max_length=128)
    notes: Optional[str] = Field(None, max_length=5000)
    status: OrderStatus = OrderStatus.draft

    @validator("expected_delivery_date")
    def validate_dates(cls, v, values):
        fixing = values.get("fixing_deadline")
        if v and fixing and fixing > v:
            raise ValueError("fixing_deadline cannot be after expected_delivery_date")
        return v


class SalesOrderCreate(SalesOrderBase):
    pass


class SalesOrderUpdate(BaseModel):
    so_number: Optional[str] = None
    deal_id: Optional[int] = None
    customer_id: Optional[int] = None
    product: Optional[str] = None
    total_quantity_mt: Optional[float] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    pricing_type: Optional[PriceType] = None
    pricing_period: Optional[str] = None
    lme_premium: Optional[float] = None
    premium: Optional[float] = None
    reference_price: Optional[str] = None
    fixing_deadline: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[OrderStatus] = None


class SalesOrderRead(SalesOrderBase):
    id: int
    created_at: datetime
    customer: Optional[CustomerRead]

    class Config:
        orm_mode = True
