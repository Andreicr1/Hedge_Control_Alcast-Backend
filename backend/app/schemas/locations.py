from datetime import datetime

from pydantic import BaseModel


class WarehouseLocationCreate(BaseModel):
    name: str
    type: str
    current_stock_mt: float
    capacity_mt: float
    active: bool = True


class WarehouseLocationUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    current_stock_mt: float | None = None
    capacity_mt: float | None = None
    active: bool | None = None


class WarehouseLocationRead(BaseModel):
    id: int
    name: str
    type: str | None
    current_stock_mt: float | None
    capacity_mt: float | None
    active: bool
    created_at: datetime

    class Config:
        orm_mode = True
