from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.domain import MarketObjectType


class MTMSnapshot(Base):
    __tablename__ = "mtm_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_type: Mapped[MarketObjectType] = mapped_column(Enum(MarketObjectType), nullable=False)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product: Mapped[str | None] = mapped_column(String(255))
    period: Mapped[str | None] = mapped_column(String(32))
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity_mt: Mapped[float] = mapped_column(Float, nullable=False)
    mtm_value: Mapped[float] = mapped_column(Float, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
