from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.models.domain import RfqStatus


@dataclass(frozen=True)
class TransitionResult:
    updated: bool
    rowcount: int


def atomic_transition_rfq_status(
    *,
    db: Session,
    rfq_id: int,
    to_status: RfqStatus,
    allowed_from: Iterable[RfqStatus],
    updates: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> TransitionResult:
    """Apply an RFQ status transition with an atomic DB guard.

    This prevents invalid/out-of-order transitions from being persisted even
    under concurrency, by performing a single conditional UPDATE:

        UPDATE rfqs
        SET status = :to_status, ...
        WHERE id = :rfq_id AND status IN (:allowed_from)

    Notes:
    - Callers control commit/rollback.
    - If you want an idempotent no-op to succeed, include `to_status` in
      `allowed_from`.
    """

    if now is None:
        now = datetime.utcnow()

    update_values: dict[str, Any] = {"status": to_status}
    if updates:
        update_values.update(updates)

    rowcount = (
        db.query(models.Rfq)
        .filter(models.Rfq.id == int(rfq_id))
        .filter(models.Rfq.status.in_(set(allowed_from)))
        .update(update_values, synchronize_session=False)
    )

    return TransitionResult(updated=rowcount > 0, rowcount=int(rowcount or 0))


def coalesce_datetime(existing_column, value: datetime):
    """Helper for SQL-side datetime coalesce (set once)."""

    return func.coalesce(existing_column, value)
