from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.cashflow import CashflowResponseRead
from app.schemas.cashflow_advanced import (
    CashflowAdvancedPreviewRequest,
    CashflowAdvancedPreviewResponse,
)
from app.schemas.cashflow_analytic import CashFlowLineRead
from app.services.cashflow_advanced_service import build_cashflow_advanced_preview
from app.services.cashflow_analytic_service import (
    CashflowAnalyticFilters,
    build_cashflow_analytic_lines,
)
from app.services.cashflow_service import build_cashflow_items

router = APIRouter(prefix="/cashflow", tags=["cashflow"])

_DB_DEP = Depends(get_db)

_START_DATE_Q = Query(None, description="Filter settlement_date >= start_date")
_END_DATE_Q = Query(None, description="Filter settlement_date <= end_date")
_AS_OF_Q = Query(None, description="Compute projected values as of this date")
_CONTRACT_ID_Q = Query(None)
_COUNTERPARTY_ID_Q = Query(None)
_DEAL_ID_Q = Query(None)
_LIMIT_Q = Query(200, ge=1, le=1000)


@router.get(
    "",
    response_model=CashflowResponseRead,
    dependencies=[Depends(require_roles(models.RoleName.financeiro, models.RoleName.auditoria))],
)
def get_cashflow(
    start_date: Optional[date] = _START_DATE_Q,
    end_date: Optional[date] = _END_DATE_Q,
    as_of: Optional[date] = _AS_OF_Q,
    contract_id: Optional[str] = _CONTRACT_ID_Q,
    counterparty_id: Optional[int] = _COUNTERPARTY_ID_Q,
    deal_id: Optional[int] = _DEAL_ID_Q,
    limit: int = _LIMIT_Q,
    db: Session = _DB_DEP,
):
    as_of_date = as_of or date.today()

    q = (
        db.query(models.Contract)
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .filter(models.Contract.settlement_date.isnot(None))
    )

    if start_date is not None:
        q = q.filter(models.Contract.settlement_date >= start_date)
    if end_date is not None:
        q = q.filter(models.Contract.settlement_date <= end_date)

    if contract_id is not None:
        q = q.filter(models.Contract.contract_id == contract_id)
    if counterparty_id is not None:
        q = q.filter(models.Contract.counterparty_id == counterparty_id)
    if deal_id is not None:
        q = q.filter(models.Contract.deal_id == deal_id)

    contracts = (
        q.order_by(models.Contract.settlement_date.asc(), models.Contract.contract_id.asc())
        .limit(limit)
        .all()
    )

    items = build_cashflow_items(db, contracts, as_of=as_of_date)
    return CashflowResponseRead(as_of=as_of_date, items=items)


@router.get(
    "/analytic",
    response_model=list[CashFlowLineRead],
    dependencies=[Depends(require_roles(models.RoleName.financeiro, models.RoleName.auditoria))],
)
def get_cashflow_analytic(
    start_date: Optional[date] = _START_DATE_Q,
    end_date: Optional[date] = _END_DATE_Q,
    as_of: Optional[date] = _AS_OF_Q,
    deal_id: Optional[int] = _DEAL_ID_Q,
    db: Session = _DB_DEP,
):
    as_of_date = as_of or date.today()
    filters = CashflowAnalyticFilters(
        start_date=start_date,
        end_date=end_date,
        deal_id=deal_id,
    )
    return build_cashflow_analytic_lines(db, as_of=as_of_date, filters=filters)


@router.post(
    "/advanced/preview",
    response_model=CashflowAdvancedPreviewResponse,
    dependencies=[Depends(require_roles(models.RoleName.financeiro, models.RoleName.auditoria))],
)
def cashflow_advanced_preview(
    payload: CashflowAdvancedPreviewRequest,
    db: Session = _DB_DEP,
):
    return build_cashflow_advanced_preview(db, payload=payload)
