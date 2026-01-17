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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MtmContractSnapshotRun(Base):
    __tablename__ = "mtm_contract_snapshot_runs"

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
        nullable=False,
        default=datetime.utcnow,
    )

    snapshots = relationship(
        "MtmContractSnapshot",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class MtmContractSnapshot(Base):
    __tablename__ = "mtm_contract_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "as_of_date",
            "currency",
            name="uq_mtm_contract_snapshots_contract_date_currency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("mtm_contract_snapshot_runs.id"),
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
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    mtm_usd: Mapped[float] = mapped_column(Float, nullable=False)
    methodology: Mapped[str | None] = mapped_column(String(128))
    references: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    run = relationship("MtmContractSnapshotRun", back_populates="snapshots")
