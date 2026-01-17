from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FinanceRiskFlagRun(Base):
    __tablename__ = "finance_risk_flag_runs"

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

    flags: Mapped[list[FinanceRiskFlag]] = relationship(
        "FinanceRiskFlag",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class FinanceRiskFlag(Base):
    __tablename__ = "finance_risk_flags"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "subject_type",
            "subject_id",
            "flag_code",
            name="uq_finance_risk_flags_run_subject_flag",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    run_id: Mapped[int] = mapped_column(
        ForeignKey("finance_risk_flag_runs.id"),
        nullable=False,
        index=True,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    deal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contract_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    flag_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    message: Mapped[str | None] = mapped_column(String(256), nullable=True)

    references: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    inputs_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    run: Mapped[FinanceRiskFlagRun] = relationship("FinanceRiskFlagRun", back_populates="flags")
