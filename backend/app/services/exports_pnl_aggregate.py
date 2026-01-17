from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app import models


def build_pnl_aggregate_csv_bytes(
    db: Session,
    *,
    as_of: datetime,
    filters: dict[str, Any] | None,
) -> bytes:
    """Builds a deterministic aggregated P&L CSV based on stored snapshots.

    Read-only: uses DealPNLSnapshot rows (no recomputation and no writes).
    """

    subject_type = (filters or {}).get("subject_type")
    subject_id = (filters or {}).get("subject_id")

    if (subject_type is None) != (subject_id is None):
        raise ValueError("subject_type and subject_id must be provided together")

    deals_q = db.query(models.Deal).order_by(models.Deal.id.asc())

    if subject_type is not None:
        if subject_type != "deal":
            raise ValueError("unsupported subject_type")
        deals_q = deals_q.filter(models.Deal.id == int(subject_id))

    deals = deals_q.all()

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "deal_id",
            "status",
            "commodity",
            "currency",
            "snapshot_timestamp",
            "physical_revenue",
            "physical_cost",
            "hedge_pnl_realized",
            "hedge_pnl_mtm",
            "net_pnl",
            "has_snapshot",
        ],
        lineterminator="\n",
    )
    writer.writeheader()

    for deal in deals:
        snap = (
            db.query(models.DealPNLSnapshot)
            .filter(models.DealPNLSnapshot.deal_id == deal.id)
            .filter(models.DealPNLSnapshot.timestamp <= as_of)
            .order_by(models.DealPNLSnapshot.timestamp.desc(), models.DealPNLSnapshot.id.desc())
            .first()
        )

        if snap is None:
            writer.writerow(
                {
                    "deal_id": str(deal.id),
                    "status": deal.status.value,
                    "commodity": deal.commodity or "",
                    "currency": deal.currency,
                    "snapshot_timestamp": "",
                    "physical_revenue": "",
                    "physical_cost": "",
                    "hedge_pnl_realized": "",
                    "hedge_pnl_mtm": "",
                    "net_pnl": "",
                    "has_snapshot": "false",
                }
            )
            continue

        writer.writerow(
            {
                "deal_id": str(deal.id),
                "status": deal.status.value,
                "commodity": deal.commodity or "",
                "currency": deal.currency,
                "snapshot_timestamp": snap.timestamp.isoformat(),
                "physical_revenue": str(float(snap.physical_revenue)),
                "physical_cost": str(float(snap.physical_cost)),
                "hedge_pnl_realized": str(float(snap.hedge_pnl_realized)),
                "hedge_pnl_mtm": str(float(snap.hedge_pnl_mtm)),
                "net_pnl": str(float(snap.net_pnl)),
                "has_snapshot": "true",
            }
        )

    return buf.getvalue().encode("utf-8")
