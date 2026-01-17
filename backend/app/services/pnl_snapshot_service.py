from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.pnl_engine import (
    PnlRealizedResult,
    PnlUnrealizedResult,
    compute_realized_pnl_for_contract,
    compute_unrealized_pnl_for_contract,
)

_PNL_RUN_VERSION = "pnl.v1.usd_only"


@dataclass(frozen=True)
class PnlSnapshotPlan:
    as_of_date: date
    filters: dict[str, Any]
    inputs_hash: str
    active_contract_ids: list[str]
    settled_contract_ids: list[str]


@dataclass(frozen=True)
class PnlSnapshotDryRunResult:
    plan: PnlSnapshotPlan
    active_contracts: int
    settled_contracts: int
    unrealized_preview: list[PnlUnrealizedResult]
    realized_preview: list[PnlRealizedResult]


@dataclass(frozen=True)
class PnlSnapshotMaterializeResult:
    run_id: int
    inputs_hash: str
    unrealized_written: int
    unrealized_updated: int
    realized_locked_written: int


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


def normalize_pnl_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    f = dict(filters or {})
    out: dict[str, Any] = {}
    for k, v in f.items():
        if v is None:
            continue
        out[str(k)] = v
    # Stable order via json canonicalization; this function just normalizes presence.
    return out


def compute_pnl_inputs_hash(*, as_of_date: date, filters: dict[str, Any] | None) -> str:
    payload = {
        "version": _PNL_RUN_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "filters": _jsonable(normalize_pnl_filters(filters)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_pnl_snapshot_plan(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> PnlSnapshotPlan:
    nf = normalize_pnl_filters(filters)
    inputs_hash = compute_pnl_inputs_hash(as_of_date=as_of_date, filters=nf)

    q = db.query(models.Contract)

    if "contract_id" in nf:
        q = q.filter(models.Contract.contract_id == str(nf["contract_id"]))
    if "deal_id" in nf:
        q = q.filter(models.Contract.deal_id == int(nf["deal_id"]))
    if "counterparty_id" in nf:
        q = q.filter(models.Contract.counterparty_id == int(nf["counterparty_id"]))

    contracts = q.order_by(models.Contract.contract_id.asc()).all()

    active_ids: list[str] = []
    settled_ids: list[str] = []

    for c in contracts:
        st = getattr(c, "status", None)
        if st == models.ContractStatus.active.value:
            active_ids.append(str(c.contract_id))
        elif st == models.ContractStatus.settled.value:
            settled_ids.append(str(c.contract_id))

    return PnlSnapshotPlan(
        as_of_date=as_of_date,
        filters=nf,
        inputs_hash=inputs_hash,
        active_contract_ids=active_ids,
        settled_contract_ids=settled_ids,
    )


def dry_run_pnl_snapshot(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> PnlSnapshotDryRunResult:
    plan = build_pnl_snapshot_plan(db, as_of_date=as_of_date, filters=filters)

    unrealized_preview: list[PnlUnrealizedResult] = []
    realized_preview: list[PnlRealizedResult] = []

    for cid in plan.active_contract_ids:
        c = db.get(models.Contract, cid)
        if c is None:
            continue
        res = compute_unrealized_pnl_for_contract(db, c, as_of_date=as_of_date)
        if res is not None:
            unrealized_preview.append(res)

    for cid in plan.settled_contract_ids:
        c = db.get(models.Contract, cid)
        if c is None:
            continue
        res = compute_realized_pnl_for_contract(db, c)
        if res is not None:
            realized_preview.append(res)

    return PnlSnapshotDryRunResult(
        plan=plan,
        active_contracts=len(plan.active_contract_ids),
        settled_contracts=len(plan.settled_contract_ids),
        unrealized_preview=unrealized_preview,
        realized_preview=realized_preview,
    )


def ensure_pnl_snapshot_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
) -> models.PnlSnapshotRun:
    plan = build_pnl_snapshot_plan(db, as_of_date=as_of_date, filters=filters)

    existing = (
        db.query(models.PnlSnapshotRun)
        .filter(models.PnlSnapshotRun.inputs_hash == plan.inputs_hash)
        .first()
    )
    if existing is not None:
        return existing

    run = models.PnlSnapshotRun(
        as_of_date=as_of_date,
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
            db.query(models.PnlSnapshotRun)
            .filter(models.PnlSnapshotRun.inputs_hash == plan.inputs_hash)
            .first()
        )
        if existing is None:
            raise
        return existing

    return run


def materialize_pnl_from_plan(
    db: Session,
    *,
    run: models.PnlSnapshotRun,
    plan: PnlSnapshotPlan,
) -> PnlSnapshotMaterializeResult:
    unrealized_written = 0
    unrealized_updated = 0
    realized_locked_written = 0

    # Unrealized snapshots (active contracts): always write one row per contract per as_of_date.
    for cid in plan.active_contract_ids:
        c = db.get(models.Contract, cid)
        if c is None:
            continue

        res = compute_unrealized_pnl_for_contract(db, c, as_of_date=plan.as_of_date)
        if res is None:
            continue

        existing = (
            db.query(models.PnlContractSnapshot)
            .filter(models.PnlContractSnapshot.contract_id == cid)
            .filter(models.PnlContractSnapshot.as_of_date == plan.as_of_date)
            .filter(models.PnlContractSnapshot.currency == "USD")
            .first()
        )

        if existing is None:
            db.add(
                models.PnlContractSnapshot(
                    run_id=int(run.id),
                    as_of_date=plan.as_of_date,
                    contract_id=cid,
                    deal_id=int(res.deal_id),
                    currency="USD",
                    unrealized_pnl_usd=float(res.unrealized_pnl_usd),
                    methodology=res.methodology,
                    data_quality_flags=res.data_quality_flags,
                    inputs_hash=plan.inputs_hash,
                )
            )
            unrealized_written += 1
        else:
            # Keep idempotent: if the row exists for this as_of_date, do not overwrite.
            unrealized_updated += 0

    # Realized locks (settled contracts): only write when final can be computed.
    for cid in plan.settled_contract_ids:
        c = db.get(models.Contract, cid)
        if c is None:
            continue
        res = compute_realized_pnl_for_contract(db, c)
        if res is None:
            continue

        existing = (
            db.query(models.PnlContractRealized)
            .filter(models.PnlContractRealized.contract_id == cid)
            .filter(models.PnlContractRealized.settlement_date == res.settlement_date)
            .filter(models.PnlContractRealized.currency == "USD")
            .first()
        )
        if existing is not None:
            continue

        db.add(
            models.PnlContractRealized(
                contract_id=cid,
                settlement_date=res.settlement_date,
                deal_id=int(res.deal_id),
                currency="USD",
                realized_pnl_usd=float(res.realized_pnl_usd),
                methodology=res.methodology,
                inputs_hash=plan.inputs_hash,
                locked_at=res.locked_at,
                source_hint={
                    "data_quality_flags": res.data_quality_flags,
                    **(res.source_hint or {}),
                },
            )
        )
        realized_locked_written += 1

    db.flush()

    return PnlSnapshotMaterializeResult(
        run_id=int(run.id),
        inputs_hash=plan.inputs_hash,
        unrealized_written=unrealized_written,
        unrealized_updated=unrealized_updated,
        realized_locked_written=realized_locked_written,
    )


def execute_pnl_snapshot_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
    dry_run: bool,
) -> PnlSnapshotDryRunResult | PnlSnapshotMaterializeResult:
    if dry_run:
        return dry_run_pnl_snapshot(db, as_of_date=as_of_date, filters=filters)

    plan = build_pnl_snapshot_plan(db, as_of_date=as_of_date, filters=filters)
    run = ensure_pnl_snapshot_run(
        db,
        as_of_date=as_of_date,
        filters=filters,
        requested_by_user_id=requested_by_user_id,
    )
    return materialize_pnl_from_plan(db, run=run, plan=plan)
