from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models


@dataclass(frozen=True)
class MonthlyNumber:
    doc_type: str
    year_month: str  # YYYYMM
    seq: int
    formatted: str


def _utc_now() -> datetime:
    return datetime.utcnow()


def format_monthly_number(*, prefix: str, seq: int, now: datetime) -> str:
    """Format: PREFIX_001-03.25 (sequence resets each month).

    - `seq` is 1-based.
    - month/year are derived from `now` in UTC.
    """

    mm = now.strftime("%m")
    yy = now.strftime("%y")
    return f"{prefix}_{seq:03d}-{mm}.{yy}"


def next_monthly_number(
    db: Session,
    *,
    doc_type: str,
    prefix: str,
    now: datetime | None = None,
    max_retries: int = 5,
) -> MonthlyNumber:
    now = now or _utc_now()
    year_month = now.strftime("%Y%m")

    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    dialect_name = getattr(dialect_name, "name", None)

    for _ in range(max_retries):
        q = db.query(models.DocumentMonthlySequence).filter(
            models.DocumentMonthlySequence.doc_type == str(doc_type),
            models.DocumentMonthlySequence.year_month == str(year_month),
        )

        # SQLite doesn't support FOR UPDATE; other DBs benefit from row locking.
        if dialect_name and str(dialect_name).lower() not in {"sqlite"}:
            q = q.with_for_update()

        row = q.first()

        if row is None:
            row = models.DocumentMonthlySequence(
                doc_type=str(doc_type),
                year_month=str(year_month),
                last_seq=0,
            )
            db.add(row)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                continue

        row.last_seq = int(row.last_seq or 0) + 1
        db.add(row)
        db.flush()

        seq = int(row.last_seq)
        return MonthlyNumber(
            doc_type=str(doc_type),
            year_month=str(year_month),
            seq=seq,
            formatted=format_monthly_number(prefix=str(prefix), seq=seq, now=now),
        )

    raise RuntimeError(
        f"Could not allocate monthly number for doc_type={doc_type} year_month={year_month}"
    )
