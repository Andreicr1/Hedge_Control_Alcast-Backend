from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.domain import HedgeStatus


class HedgeExposureLink(BaseModel):
    exposure_id: int
    quantity_mt: float = Field(..., gt=0)


class HedgeCreateManual(BaseModel):
    counterparty_id: int
    quantity_mt: float = Field(..., gt=0)
    contract_price: float = Field(..., gt=0)
    period: str = Field(..., min_length=1, max_length=20)
    instrument: str = Field(..., max_length=128)
    maturity_date: date
    reference_code: str | None = Field(None, max_length=128)
    workflow_request_id: int | None = None
    exposures: list[HedgeExposureLink]


class HedgeReadManual(BaseModel):
    id: int
    status: HedgeStatus
    instrument: str | None
    maturity_date: date | None
    reference_code: str | None
    created_at: datetime

    class Config:
        orm_mode = True
