from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LMEPrice(Base):
    __tablename__ = "lme_prices"

    # Keep as string for cross-db compatibility (SQLite tests/dev), while still storing UUID values.
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    # "live" or "official"
    price_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    ts_price: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ts_ingest: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[str] = mapped_column(String(64), nullable=False)
