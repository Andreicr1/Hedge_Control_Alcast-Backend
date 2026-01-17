from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CashflowBaselineRun(Base):
    __tablename__ = "cashflow_baseline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scope_filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    items: Mapped[list[CashflowBaselineItem]] = relationship(
        "CashflowBaselineItem",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class CashflowBaselineItem(Base):
    __tablename__ = "cashflow_baseline_items"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "as_of_date",
            "currency",
            name="uq_cashflow_baseline_items_contract_date_currency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    run_id: Mapped[int] = mapped_column(
        ForeignKey("cashflow_baseline_runs.id"),
        nullable=False,
        index=True,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    contract_id: Mapped[str] = mapped_column(
        ForeignKey("contracts.contract_id"),
        nullable=False,
        index=True,
    )
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rfq_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    counterparty_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="USD")

    projected_value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_methodology: Mapped[str | None] = mapped_column(String(128), nullable=True)
    projected_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)

    final_value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_methodology: Mapped[str | None] = mapped_column(String(128), nullable=True)

    observation_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    observation_end_used: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_published_cash_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    data_quality_flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    references: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[CashflowBaselineRun] = relationship("CashflowBaselineRun", back_populates="items")
