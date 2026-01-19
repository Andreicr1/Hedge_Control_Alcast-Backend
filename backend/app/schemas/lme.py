from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, validator


LmeSymbol = Literal["P3Y00", "P4Y00", "Q7Y00", "^USDBRL"]
LmePriceType = Literal["live", "close", "official"]


_SYMBOL_TO_ALLOWED_TYPES: dict[str, set[str]] = {
    "P3Y00": {"live", "close"},
    "P4Y00": {"live", "close"},
    "Q7Y00": {"official"},
    "^USDBRL": {"live", "close"},
}


class LMEPriceIngest(BaseModel):
    symbol: LmeSymbol
    name: str = Field(..., min_length=1, max_length=128)
    market: str = Field(..., min_length=1, max_length=16)
    price: Decimal = Field(..., gt=0)
    price_type: LmePriceType
    ts_price: datetime
    source: str = Field(..., min_length=1, max_length=64)

    @validator("market")
    def _market_must_match_symbol(cls, v: str, values) -> str:
        market = str(v).strip().upper()
        symbol = str(values.get("symbol") or "").strip()

        if symbol == "^USDBRL":
            if market != "FX":
                raise ValueError("market must be FX for ^USDBRL")
            return "FX"

        if market != "LME":
            raise ValueError("market must be LME")
        return "LME"

    @validator("price_type")
    def _price_type_matches_symbol(cls, v: str, values):
        symbol = values.get("symbol")
        if symbol:
            allowed = _SYMBOL_TO_ALLOWED_TYPES.get(str(symbol), set())
            if v not in allowed:
                raise ValueError("price_type mismatch for symbol")
        return v

    @validator("ts_price")
    def _ts_price_must_be_tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts_price must be timezone-aware")
        # normalize to UTC
        return v.astimezone(timezone.utc)


class LMEPricePoint(BaseModel):
    date: str
    price: float


class LMEOfficialLatest(BaseModel):
    symbol: str
    price: float
    ts: str
    date: str


class LMELiveResponse(BaseModel):
    cash: dict
    three_month: dict
