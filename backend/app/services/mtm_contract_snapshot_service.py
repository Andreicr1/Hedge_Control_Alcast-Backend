from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.services.contract_mtm_service import ContractMtmResult, compute_mtm_for_contract_avg

_MTM_CONTRACT_RUN_VERSION = "mtm.contract_snapshot.v1.usd_only"


@dataclass(frozen=True)
class MtmContractSnapshotPlan:
    as_of_date: date
    filters: dict[str, Any]
    inputs_hash: str
    active_contract_ids: list[str]


@dataclass(frozen=True)
class MtmContractSnapshotDryRunResult:
    plan: MtmContractSnapshotPlan
    active_contracts: int


@dataclass(frozen=True)
class MtmContractSnapshotMaterializeResult:
    run_id: int
    inputs_hash: str
    written: int
    skipped_existing: int
    skipped_not_computable: int
    snapshot_ids: list[int]


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


def normalize_mtm_contract_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    f = dict(filters or {})
    out: dict[str, Any] = {}
    for k, v in f.items():
        if v is None:
            continue
        out[str(k)] = v
    return out


def compute_mtm_contract_inputs_hash(*, as_of_date: date, filters: dict[str, Any] | None) -> str:
    payload = {
        "version": _MTM_CONTRACT_RUN_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "filters": _jsonable(normalize_mtm_contract_filters(filters)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_mtm_contract_snapshot_plan(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> MtmContractSnapshotPlan:
    nf = normalize_mtm_contract_filters(filters)
    inputs_hash = compute_mtm_contract_inputs_hash(as_of_date=as_of_date, filters=nf)

    q = db.query(models.Contract).filter(
        models.Contract.status == models.ContractStatus.active.value
    )

    if "contract_id" in nf:
        q = q.filter(models.Contract.contract_id == str(nf["contract_id"]))
    if "deal_id" in nf:
        q = q.filter(models.Contract.deal_id == int(nf["deal_id"]))
    if "counterparty_id" in nf:
        q = q.filter(models.Contract.counterparty_id == int(nf["counterparty_id"]))

    contracts = q.order_by(models.Contract.contract_id.asc()).all()
    active_ids = [str(c.contract_id) for c in contracts]

    return MtmContractSnapshotPlan(
        as_of_date=as_of_date,
        filters=nf,
        inputs_hash=inputs_hash,
        active_contract_ids=active_ids,
    )


def dry_run_mtm_contract_snapshot(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
) -> MtmContractSnapshotDryRunResult:
    plan = build_mtm_contract_snapshot_plan(db, as_of_date=as_of_date, filters=filters)
    return MtmContractSnapshotDryRunResult(
        plan=plan,
        active_contracts=len(plan.active_contract_ids),
    )


def ensure_mtm_contract_snapshot_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
) -> models.MtmContractSnapshotRun:
    plan = build_mtm_contract_snapshot_plan(db, as_of_date=as_of_date, filters=filters)

    existing = (
        db.query(models.MtmContractSnapshotRun)
        .filter(models.MtmContractSnapshotRun.inputs_hash == plan.inputs_hash)
        .first()
    )
    if existing is not None:
        return existing

    run = models.MtmContractSnapshotRun(
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
            db.query(models.MtmContractSnapshotRun)
            .filter(models.MtmContractSnapshotRun.inputs_hash == plan.inputs_hash)
            .first()
        )
        if existing is None:
            raise
        return existing

    return run


def _references_from_result(res: ContractMtmResult) -> dict[str, Any]:
    return {
        "as_of_date": res.as_of_date.isoformat(),
        "methodology": res.methodology,
        "price_used": float(res.price_used) if res.price_used is not None else None,
        "observation_start": res.observation_start.isoformat() if res.observation_start else None,
        "observation_end_used": (
            res.observation_end_used.isoformat() if res.observation_end_used else None
        ),
        "last_published_cash_date": (
            res.last_published_cash_date.isoformat() if res.last_published_cash_date else None
        ),
    }


def materialize_mtm_contract_from_plan(
    db: Session,
    *,
    run: models.MtmContractSnapshotRun,
    plan: MtmContractSnapshotPlan,
) -> MtmContractSnapshotMaterializeResult:
    written = 0
    skipped_existing = 0
    skipped_not_computable = 0

    for cid in plan.active_contract_ids:
        c = db.get(models.Contract, cid)
        if c is None:
            continue

        existing = (
            db.query(models.MtmContractSnapshot)
            .filter(models.MtmContractSnapshot.contract_id == cid)
            .filter(models.MtmContractSnapshot.as_of_date == plan.as_of_date)
            .filter(models.MtmContractSnapshot.currency == "USD")
            .first()
        )
        if existing is not None:
            skipped_existing += 1
            continue

        res = compute_mtm_for_contract_avg(db, c, as_of_date=plan.as_of_date)
        if res is None:
            skipped_not_computable += 1
            continue

        db.add(
            models.MtmContractSnapshot(
                run_id=int(run.id),
                as_of_date=plan.as_of_date,
                contract_id=cid,
                deal_id=int(c.deal_id),
                currency="USD",
                mtm_usd=float(res.mtm_usd),
                methodology=res.methodology,
                references=_references_from_result(res),
                inputs_hash=plan.inputs_hash,
            )
        )
        written += 1

    db.flush()

    snapshots = (
        db.query(models.MtmContractSnapshot)
        .filter(models.MtmContractSnapshot.run_id == int(run.id))
        .order_by(models.MtmContractSnapshot.contract_id.asc(), models.MtmContractSnapshot.id.asc())
        .all()
    )

    return MtmContractSnapshotMaterializeResult(
        run_id=int(run.id),
        inputs_hash=plan.inputs_hash,
        written=written,
        skipped_existing=skipped_existing,
        skipped_not_computable=skipped_not_computable,
        snapshot_ids=[int(s.id) for s in snapshots],
    )


def execute_mtm_contract_snapshot_run(
    db: Session,
    *,
    as_of_date: date,
    filters: dict[str, Any] | None,
    requested_by_user_id: int | None,
    dry_run: bool,
) -> MtmContractSnapshotDryRunResult | MtmContractSnapshotMaterializeResult:
    if dry_run:
        return dry_run_mtm_contract_snapshot(db, as_of_date=as_of_date, filters=filters)

    plan = build_mtm_contract_snapshot_plan(db, as_of_date=as_of_date, filters=filters)
    run = ensure_mtm_contract_snapshot_run(
        db,
        as_of_date=as_of_date,
        filters=filters,
        requested_by_user_id=requested_by_user_id,
    )
    return materialize_mtm_contract_from_plan(db, run=run, plan=plan)
