from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.cashflow_baseline_service import compute_cashflow_baseline_inputs_hash
from app.services.pnl_snapshot_service import normalize_pnl_filters

_FINANCE_RISK_FLAGS_RUN_VERSION = "finance.risk_flags.daily.v1"


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(vv) for k, vv in sorted(v.items(), key=lambda x: str(x[0]))}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return str(v)


def compute_finance_risk_flags_inputs_hash(
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> str:
    payload = {
        "version": _FINANCE_RISK_FLAGS_RUN_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "filters": _jsonable(normalize_pnl_filters(filters)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class FinanceRiskFlagsPlan:
    as_of_date: date
    filters: dict[str, Any]
    inputs_hash: str


def build_finance_risk_flags_plan(
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> FinanceRiskFlagsPlan:
    nf = normalize_pnl_filters(filters)
    inputs_hash = compute_finance_risk_flags_inputs_hash(as_of_date=as_of_date, filters=nf)
    return FinanceRiskFlagsPlan(as_of_date=as_of_date, filters=nf, inputs_hash=inputs_hash)


def ensure_finance_risk_flags_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
) -> models.FinanceRiskFlagRun:
    plan = build_finance_risk_flags_plan(as_of_date=as_of_date, filters=filters)

    existing = (
        db.query(models.FinanceRiskFlagRun)
        .filter(models.FinanceRiskFlagRun.inputs_hash == plan.inputs_hash)
        .first()
    )
    if existing is not None:
        return existing

    run = models.FinanceRiskFlagRun(
        as_of_date=plan.as_of_date,
        scope_filters=plan.filters,
        inputs_hash=plan.inputs_hash,
        requested_by_user_id=requested_by_user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.FinanceRiskFlagRun)
            .filter(models.FinanceRiskFlagRun.inputs_hash == plan.inputs_hash)
            .first()
        )
        if existing is None:
            raise
        return existing

    return run


@dataclass(frozen=True)
class FinanceRiskFlagsDryRunResult:
    plan: FinanceRiskFlagsPlan


@dataclass(frozen=True)
class FinanceRiskFlagsMaterializeResult:
    run_id: int
    inputs_hash: str
    written: int
    skipped_existing: int
    flag_ids: list[int]


_FLAG_SEVERITY: dict[str, str] = {
    "mtm_not_available": "error",
    "pnl_not_available": "error",
    "missing_settlement_date": "warning",
    "final_not_available": "warning",
    "data_incomplete": "warning",
}


def execute_finance_risk_flags_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
    dry_run: bool,
) -> FinanceRiskFlagsDryRunResult | FinanceRiskFlagsMaterializeResult:
    plan = build_finance_risk_flags_plan(as_of_date=as_of_date, filters=filters)

    if dry_run:
        return FinanceRiskFlagsDryRunResult(plan=plan)

    # Derive baseline run from canonical inputs.
    baseline_inputs_hash = compute_cashflow_baseline_inputs_hash(
        as_of_date=as_of_date,
        filters=plan.filters,
    )
    baseline_run = (
        db.query(models.CashflowBaselineRun)
        .filter(models.CashflowBaselineRun.inputs_hash == baseline_inputs_hash)
        .first()
    )
    if baseline_run is None:
        raise RuntimeError("Cashflow baseline run not found for risk flags")

    run = ensure_finance_risk_flags_run(
        db,
        as_of_date=plan.as_of_date,
        filters=plan.filters,
        requested_by_user_id=requested_by_user_id,
    )

    written = 0
    skipped_existing = 0
    flag_ids: list[int] = []

    items = (
        db.query(models.CashflowBaselineItem)
        .filter(models.CashflowBaselineItem.run_id == int(baseline_run.id))
        .order_by(models.CashflowBaselineItem.contract_id.asc())
        .all()
    )

    for item in items:
        flags = list(item.data_quality_flags or [])
        for code in flags:
            existing = (
                db.query(models.FinanceRiskFlag)
                .filter(models.FinanceRiskFlag.run_id == int(run.id))
                .filter(models.FinanceRiskFlag.subject_type == "contract")
                .filter(models.FinanceRiskFlag.subject_id == str(item.contract_id))
                .filter(models.FinanceRiskFlag.flag_code == str(code))
                .first()
            )
            if existing is not None:
                skipped_existing += 1
                flag_ids.append(int(existing.id))
                continue

            ref = dict(item.references or {})
            ref.update(
                {
                    "cashflow_baseline_run_id": int(baseline_run.id),
                    "cashflow_baseline_item_id": int(item.id),
                }
            )

            row = models.FinanceRiskFlag(
                run_id=int(run.id),
                as_of_date=plan.as_of_date,
                subject_type="contract",
                subject_id=str(item.contract_id),
                deal_id=int(item.deal_id) if item.deal_id is not None else None,
                contract_id=str(item.contract_id),
                flag_code=str(code),
                severity=_FLAG_SEVERITY.get(str(code)),
                message=None,
                references=ref,
                inputs_hash=plan.inputs_hash,
                created_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.flush()
            written += 1
            flag_ids.append(int(row.id))

    return FinanceRiskFlagsMaterializeResult(
        run_id=int(run.id),
        inputs_hash=str(plan.inputs_hash),
        written=written,
        skipped_existing=skipped_existing,
        flag_ids=flag_ids,
    )
