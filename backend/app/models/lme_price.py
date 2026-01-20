from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LMEPrice(Base):
    __tablename__ = "lme_prices"

    # Use a UUID type so Postgres stores/compares correctly, while SQLAlchemy still
    # provides cross-db portability for SQLite-based tests.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    # "live" or "official"
    price_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    ts_price: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ts_ingest: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[str] = mapped_column(String(64), nullable=False)
