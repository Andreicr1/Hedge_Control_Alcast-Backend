from datetime import date
from typing import Optional

from pydantic import BaseModel


class InventoryItem(BaseModel):
    lot_code: str
    product: str
    available_tons: float
    committed_links: int
    committed_tons: float
    location: Optional[str] = ""
    avg_cost: Optional[float] = None
    arrival_date: Optional[date] = None
    mtm_value: Optional[float] = None
    purchase_order_id: int
