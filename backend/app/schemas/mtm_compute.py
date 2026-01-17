from typing import Optional

from pydantic import BaseModel

from app.models.domain import MarketObjectType


class MtmComputeRequest(BaseModel):
    object_type: MarketObjectType
    object_id: Optional[int]  # for portfolio, object_id can be null/ignored
    fx_symbol: Optional[str] = None
    pricing_source: Optional[str] = None
    haircut_pct: Optional[float] = None
    price_shift: Optional[float] = None


class MtmComputeResponse(BaseModel):
    institutional_layer: str = "proxy"
    is_proxy: bool = True

    object_type: MarketObjectType
    object_id: int
    mtm_value: Optional[float]
    fx_rate: Optional[float] = None
    scenario_mtm_value: Optional[float] = None
    haircut_pct: Optional[float] = None
    price_shift: Optional[float] = None
