from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.contract_mtm_service import compute_settlement_value_for_contract_avg
from app.services.pnl_snapshot_service import normalize_pnl_filters

_CASHFLOW_BASELINE_RUN_VERSION = "cashflow.baseline.daily.v1"


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


def compute_cashflow_baseline_inputs_hash(
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> str:
    payload = {
        "version": _CASHFLOW_BASELINE_RUN_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "filters": _jsonable(normalize_pnl_filters(filters)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class CashflowBaselinePlan:
    as_of_date: date
    filters: dict[str, Any]
    inputs_hash: str
    contract_ids: list[str]


def build_cashflow_baseline_plan(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> CashflowBaselinePlan:
    nf = normalize_pnl_filters(filters)
    inputs_hash = compute_cashflow_baseline_inputs_hash(as_of_date=as_of_date, filters=nf)

    q = db.query(models.Contract)

    if "contract_id" in nf:
        q = q.filter(models.Contract.contract_id == str(nf["contract_id"]))
    if "deal_id" in nf:
        q = q.filter(models.Contract.deal_id == int(nf["deal_id"]))
    if "counterparty_id" in nf:
        q = q.filter(models.Contract.counterparty_id == int(nf["counterparty_id"]))

    if "settlement_date_from" in nf:
        q = q.filter(models.Contract.settlement_date >= nf["settlement_date_from"])
    if "settlement_date_to" in nf:
        q = q.filter(models.Contract.settlement_date <= nf["settlement_date_to"])

    contracts = q.order_by(models.Contract.contract_id.asc()).all()

    contract_ids: list[str] = []
    for c in contracts:
        st = getattr(c, "status", None)
        if st in {models.ContractStatus.active.value, models.ContractStatus.settled.value}:
            contract_ids.append(str(c.contract_id))

    return CashflowBaselinePlan(
        as_of_date=as_of_date,
        filters=nf,
        inputs_hash=inputs_hash,
        contract_ids=contract_ids,
    )


def ensure_cashflow_baseline_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
) -> models.CashflowBaselineRun:
    plan = build_cashflow_baseline_plan(db, as_of_date=as_of_date, filters=filters)

    existing = (
        db.query(models.CashflowBaselineRun)
        .filter(models.CashflowBaselineRun.inputs_hash == plan.inputs_hash)
        .first()
    )
    if existing is not None:
        return existing

    run = models.CashflowBaselineRun(
        as_of_date=plan.as_of_date,
        scope_filters=plan.filters,
        inputs_hash=plan.inputs_hash,
        requested_by_user_id=requested_by_user_id,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.CashflowBaselineRun)
            .filter(models.CashflowBaselineRun.inputs_hash == plan.inputs_hash)
            .first()
        )
        if existing is None:
            raise
        return existing

    return run


@dataclass(frozen=True)
class CashflowBaselineDryRunResult:
    plan: CashflowBaselinePlan
    contracts: int


@dataclass(frozen=True)
class CashflowBaselineMaterializeResult:
    run_id: int
    inputs_hash: str
    written: int
    skipped_existing: int
    item_ids: list[int]

    mtm_missing: int
    pnl_missing: int
    missing_settlement_date: int


def _date_from_iso(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def execute_cashflow_baseline_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
    dry_run: bool,
) -> CashflowBaselineDryRunResult | CashflowBaselineMaterializeResult:
    plan = build_cashflow_baseline_plan(db, as_of_date=as_of_date, filters=filters)

    if dry_run:
        return CashflowBaselineDryRunResult(plan=plan, contracts=len(plan.contract_ids))

    run = ensure_cashflow_baseline_run(
        db,
        as_of_date=plan.as_of_date,
        filters=plan.filters,
        requested_by_user_id=requested_by_user_id,
    )

    written = 0
    skipped_existing = 0
    mtm_missing = 0
    pnl_missing = 0
    missing_settlement_date = 0

    item_ids: list[int] = []

    for cid in plan.contract_ids:
        c = db.get(models.Contract, cid)
        if c is None:
            continue

        existing = (
            db.query(models.CashflowBaselineItem)
            .filter(models.CashflowBaselineItem.contract_id == cid)
            .filter(models.CashflowBaselineItem.as_of_date == plan.as_of_date)
            .filter(models.CashflowBaselineItem.currency == "USD")
            .first()
        )
        if existing is not None:
            skipped_existing += 1
            item_ids.append(int(existing.id))
            continue

        flags: list[str] = []

        if c.settlement_date is None:
            flags.append("missing_settlement_date")
            missing_settlement_date += 1

        mtm = (
            db.query(models.MtmContractSnapshot)
            .filter(models.MtmContractSnapshot.contract_id == cid)
            .filter(models.MtmContractSnapshot.as_of_date == plan.as_of_date)
            .filter(models.MtmContractSnapshot.currency == "USD")
            .first()
        )
        if mtm is None:
            flags.append("mtm_not_available")
            mtm_missing += 1

        pnl = (
            db.query(models.PnlContractSnapshot)
            .filter(models.PnlContractSnapshot.contract_id == cid)
            .filter(models.PnlContractSnapshot.as_of_date == plan.as_of_date)
            .filter(models.PnlContractSnapshot.currency == "USD")
            .first()
        )
        if pnl is None:
            flags.append("pnl_not_available")
            pnl_missing += 1

        references: dict[str, Any] = {
            "mtm_contract_snapshot_id": int(mtm.id) if mtm is not None else None,
            "mtm_contract_snapshot_run_id": int(mtm.run_id) if mtm is not None else None,
            "pnl_contract_snapshot_id": int(pnl.id) if pnl is not None else None,
            "pnl_snapshot_run_id": int(pnl.run_id) if pnl is not None else None,
        }

        observation_start: date | None = None
        observation_end_used: date | None = None
        last_published_cash_date: date | None = None
        projected_methodology: str | None = None
        projected_value_usd: float | None = None

        if mtm is not None:
            projected_value_usd = float(mtm.mtm_usd)
            projected_methodology = str(mtm.methodology) if mtm.methodology else None

            mtm_refs = dict(mtm.references or {})
            references["mtm_references"] = mtm_refs
            observation_start = _date_from_iso(mtm_refs.get("observation_start"))
            observation_end_used = _date_from_iso(mtm_refs.get("observation_end_used"))
            last_published_cash_date = _date_from_iso(mtm_refs.get("last_published_cash_date"))

        final_value_usd: float | None = None
        final_methodology: str | None = None

        if c.settlement_date is not None and plan.as_of_date >= c.settlement_date:
            final_res = compute_settlement_value_for_contract_avg(db, c)
            if final_res is None:
                flags.append("final_not_available")
            else:
                final_value_usd = float(final_res.mtm_usd)
                final_methodology = str(final_res.methodology) if final_res.methodology else None

        if flags and "data_incomplete" not in flags:
            flags.append("data_incomplete")

        item = models.CashflowBaselineItem(
            run_id=int(run.id),
            as_of_date=plan.as_of_date,
            contract_id=cid,
            deal_id=int(c.deal_id),
            rfq_id=int(c.rfq_id),
            counterparty_id=int(c.counterparty_id) if c.counterparty_id is not None else None,
            settlement_date=c.settlement_date,
            currency="USD",
            projected_value_usd=projected_value_usd,
            projected_methodology=projected_methodology,
            projected_as_of=plan.as_of_date,
            final_value_usd=final_value_usd,
            final_methodology=final_methodology,
            observation_start=observation_start,
            observation_end_used=observation_end_used,
            last_published_cash_date=last_published_cash_date,
            data_quality_flags=list(flags),
            references=references,
            inputs_hash=plan.inputs_hash,
        )
        db.add(item)
        db.flush()
        written += 1
        item_ids.append(int(item.id))

    return CashflowBaselineMaterializeResult(
        run_id=int(run.id),
        inputs_hash=str(plan.inputs_hash),
        written=written,
        skipped_existing=skipped_existing,
        item_ids=item_ids,
        mtm_missing=mtm_missing,
        pnl_missing=pnl_missing,
        missing_settlement_date=missing_settlement_date,
    )
