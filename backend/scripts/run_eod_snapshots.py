from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Any

from app.database import SessionLocal
from app.services.cashflow_baseline_service import execute_cashflow_baseline_run
from app.services.pnl_snapshot_service import execute_pnl_snapshot_run


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Invalid date, expected YYYY-MM-DD") from exc


def _parse_filters(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        obj = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("Invalid JSON for --filters-json") from exc
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise argparse.ArgumentTypeError("--filters-json must be a JSON object (dict)")
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(
        description="EOD materialization runner: P&L snapshots + Cashflow baseline (read models)."
    )
    parser.add_argument("--as-of", type=_parse_iso_date, default=date.today())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--filters-json", type=_parse_filters, default={})
    args = parser.parse_args()

    as_of_date: date = args.as_of
    dry_run: bool = bool(args.dry_run)
    filters: dict[str, Any] = dict(args.filters_json or {})

    db = SessionLocal()
    try:
        pnl_res = execute_pnl_snapshot_run(
            db,
            as_of_date=as_of_date,
            filters=filters,
            requested_by_user_id=None,
            dry_run=dry_run,
        )
        if not dry_run:
            db.commit()

        cashflow_res = execute_cashflow_baseline_run(
            db,
            as_of_date=as_of_date,
            filters=filters,
            requested_by_user_id=None,
            dry_run=dry_run,
        )
        if not dry_run:
            db.commit()

        print(
            json.dumps(
                {
                    "as_of_date": as_of_date.isoformat(),
                    "dry_run": dry_run,
                    "filters": filters,
                    "pnl": getattr(pnl_res, "__dict__", str(pnl_res)),
                    "cashflow_baseline": getattr(cashflow_res, "__dict__", str(cashflow_res)),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

