from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.pnl import (
    PnlAggregateResponse,
    PnlContractDetailResponse,
    PnlContractRealizedRead,
    PnlContractSnapshotRead,
    PnlDealAggregateRow,
    PnlRealizedPreview,
    PnlSnapshotDryRunRead,
    PnlSnapshotExecuteResponse,
    PnlSnapshotMaterializeRead,
    PnlSnapshotPlanRead,
    PnlSnapshotRequest,
    PnlUnrealizedPreview,
)
from app.services.pnl_snapshot_service import (
    PnlSnapshotDryRunResult,
    PnlSnapshotMaterializeResult,
    compute_pnl_inputs_hash,
    execute_pnl_snapshot_run,
    normalize_pnl_filters,
)
from app.services.pnl_timeline import emit_pnl_snapshot_created
from app.services.timeline_emitters import correlation_id_from_request_id

router = APIRouter(prefix="/pnl", tags=["pnl"])


_db_dep = Depends(get_db)
_finance_user_dep = Depends(require_roles(models.RoleName.financeiro, models.RoleName.admin))
_finance_or_audit_user_dep = Depends(
    require_roles(models.RoleName.financeiro, models.RoleName.auditoria, models.RoleName.admin)
)


def _as_execute_response(
    res: Union[PnlSnapshotDryRunResult, PnlSnapshotMaterializeResult],
) -> PnlSnapshotExecuteResponse:
    if isinstance(res, PnlSnapshotDryRunResult):
        return PnlSnapshotDryRunRead(
            plan=PnlSnapshotPlanRead(
                as_of_date=res.plan.as_of_date,
                filters=res.plan.filters,
                inputs_hash=res.plan.inputs_hash,
                active_contract_ids=list(res.plan.active_contract_ids),
                settled_contract_ids=list(res.plan.settled_contract_ids),
            ),
            active_contracts=res.active_contracts,
            settled_contracts=res.settled_contracts,
            unrealized_preview=[
                PnlUnrealizedPreview(
                    contract_id=x.contract_id,
                    deal_id=x.deal_id,
                    as_of_date=x.as_of_date,
                    unrealized_pnl_usd=x.unrealized_pnl_usd,
                    methodology=x.methodology,
                    data_quality_flags=list(x.data_quality_flags),
                )
                for x in res.unrealized_preview
            ],
            realized_preview=[
                PnlRealizedPreview(
                    contract_id=x.contract_id,
                    deal_id=x.deal_id,
                    settlement_date=x.settlement_date,
                    realized_pnl_usd=x.realized_pnl_usd,
                    methodology=x.methodology,
                    data_quality_flags=list(x.data_quality_flags),
                    locked_at=x.locked_at,
                )
                for x in res.realized_preview
            ],
        )

    return PnlSnapshotMaterializeRead(
        run_id=res.run_id,
        inputs_hash=res.inputs_hash,
        unrealized_written=res.unrealized_written,
        unrealized_updated=res.unrealized_updated,
        realized_locked_written=res.realized_locked_written,
    )


@router.post(
    "/snapshots",
    response_model=PnlSnapshotExecuteResponse,
    status_code=status.HTTP_200_OK,
)
def create_pnl_snapshot(
    request: Request,
    payload: PnlSnapshotRequest,
    db: Session = _db_dep,
    current_user: models.User = _finance_user_dep,
):
    nf = normalize_pnl_filters(payload.filters)
    inputs_hash = compute_pnl_inputs_hash(as_of_date=payload.as_of_date, filters=nf)

    try:
        res = execute_pnl_snapshot_run(
            db,
            as_of_date=payload.as_of_date,
            filters=nf,
            requested_by_user_id=getattr(current_user, "id", None),
            dry_run=bool(payload.dry_run),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(res, PnlSnapshotDryRunResult):
        return _as_execute_response(res)

    # Post-commit timeline: P&L writes must be persisted before emitting.
    db.commit()

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    emit_pnl_snapshot_created(
        db=db,
        run_id=res.run_id,
        inputs_hash=inputs_hash,
        as_of_date=payload.as_of_date,
        filters=nf,
        correlation_id=correlation_id,
        actor_user_id=getattr(current_user, "id", None),
        meta={
            "unrealized_written": res.unrealized_written,
            "realized_locked_written": res.realized_locked_written,
        },
    )

    return _as_execute_response(res)


@router.get("", response_model=PnlAggregateResponse)
def get_pnl_aggregated(
    db: Session = _db_dep,
    current_user: models.User = _finance_or_audit_user_dep,
    as_of_date: Optional[date] = None,
    deal_id: Optional[int] = None,
    contract_id: Optional[str] = None,
    counterparty_id: Optional[int] = None,
):
    if as_of_date is None:
        as_of_date = date.today()

    snapshots_q = db.query(models.PnlContractSnapshot).filter(
        models.PnlContractSnapshot.as_of_date == as_of_date
    )
    if deal_id is not None:
        snapshots_q = snapshots_q.filter(models.PnlContractSnapshot.deal_id == int(deal_id))
    if contract_id is not None:
        snapshots_q = snapshots_q.filter(models.PnlContractSnapshot.contract_id == str(contract_id))

    if counterparty_id is not None:
        contract_ids = (
            db.query(models.Contract.contract_id)
            .filter(models.Contract.counterparty_id == int(counterparty_id))
            .subquery()
        )
        snapshots_q = snapshots_q.filter(models.PnlContractSnapshot.contract_id.in_(contract_ids))

    snapshots = snapshots_q.all()

    realized_q = db.query(models.PnlContractRealized).filter(
        models.PnlContractRealized.settlement_date <= as_of_date
    )
    if deal_id is not None:
        realized_q = realized_q.filter(models.PnlContractRealized.deal_id == int(deal_id))
    if contract_id is not None:
        realized_q = realized_q.filter(models.PnlContractRealized.contract_id == str(contract_id))

    if counterparty_id is not None:
        contract_ids = (
            db.query(models.Contract.contract_id)
            .filter(models.Contract.counterparty_id == int(counterparty_id))
            .subquery()
        )
        realized_q = realized_q.filter(models.PnlContractRealized.contract_id.in_(contract_ids))

    realized_rows = realized_q.all()

    unreal_by_deal: Dict[int, float] = defaultdict(float)
    for s in snapshots:
        unreal_by_deal[int(s.deal_id)] += float(s.unrealized_pnl_usd or 0.0)

    real_by_deal: Dict[int, float] = defaultdict(float)
    for r in realized_rows:
        real_by_deal[int(r.deal_id)] += float(r.realized_pnl_usd or 0.0)

    deal_ids = sorted(set(unreal_by_deal.keys()) | set(real_by_deal.keys()))

    rows: List[PnlDealAggregateRow] = []
    unreal_total = 0.0
    real_total = 0.0

    for did in deal_ids:
        u = float(unreal_by_deal.get(did, 0.0))
        rr = float(real_by_deal.get(did, 0.0))
        rows.append(
            PnlDealAggregateRow(
                deal_id=int(did),
                currency="USD",
                unrealized_pnl_usd=u,
                realized_pnl_usd=rr,
                total_pnl_usd=u + rr,
            )
        )
        unreal_total += u
        real_total += rr

    return PnlAggregateResponse(
        as_of_date=as_of_date,
        currency="USD",
        rows=rows,
        unrealized_total_usd=unreal_total,
        realized_total_usd=real_total,
        total_pnl_usd=unreal_total + real_total,
    )


@router.get("/contracts/{contract_id}", response_model=PnlContractDetailResponse)
def get_pnl_contract_detail(
    contract_id: str,
    db: Session = _db_dep,
    current_user: models.User = _finance_or_audit_user_dep,
    as_of_date: Optional[date] = None,
):
    if as_of_date is None:
        as_of_date = date.today()

    unreal = (
        db.query(models.PnlContractSnapshot)
        .filter(models.PnlContractSnapshot.contract_id == str(contract_id))
        .filter(models.PnlContractSnapshot.as_of_date == as_of_date)
        .filter(models.PnlContractSnapshot.currency == "USD")
        .first()
    )

    realized_locks = (
        db.query(models.PnlContractRealized)
        .filter(models.PnlContractRealized.contract_id == str(contract_id))
        .filter(models.PnlContractRealized.currency == "USD")
        .filter(models.PnlContractRealized.settlement_date <= as_of_date)
        .order_by(models.PnlContractRealized.settlement_date.asc())
        .all()
    )

    if unreal is None and not realized_locks:
        if db.get(models.Contract, str(contract_id)) is None:
            raise HTTPException(status_code=404, detail="Contract not found")

    realized_total = sum(float(r.realized_pnl_usd or 0.0) for r in realized_locks)
    unreal_value = float(getattr(unreal, "unrealized_pnl_usd", 0.0) or 0.0)

    return PnlContractDetailResponse(
        contract_id=str(contract_id),
        as_of_date=as_of_date,
        currency="USD",
        unrealized=PnlContractSnapshotRead.from_orm(unreal) if unreal is not None else None,
        realized_locks=[PnlContractRealizedRead.from_orm(x) for x in realized_locks],
        realized_total_usd=realized_total,
        total_pnl_usd=realized_total + unreal_value,
    )
