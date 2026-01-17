from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.settlements import SettlementItemRead
from app.services.contract_mtm_service import (
    compute_mtm_for_contract_avg,
    compute_settlement_value_for_contract_avg,
)

router = APIRouter(prefix="/contracts/settlements", tags=["settlements"])


def _fallback_settlement_value_from_hedge(h: models.Hedge) -> float | None:
    """
    Legacy fallback only. Domain rule: MTM should be computed on Contracts.
    """
    if h.mtm_value is not None:
        return float(h.mtm_value)
    if h.current_market_price is None:
        return None
    return float((h.current_market_price - h.contract_price) * (h.quantity_mt or 0))


def _contract_mtm_today_usd(db: Session, c: models.Contract, today: date) -> float | None:
    # Start with AVG rule; extendable for other price types later.
    res = compute_mtm_for_contract_avg(db, c, as_of_date=today)
    return float(res.mtm_usd) if res else None


@router.get(
    "/today",
    response_model=List[SettlementItemRead],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def get_today(db: Session = Depends(get_db)):
    today = date.today()
    out: List[SettlementItemRead] = []

    contracts = (
        db.query(models.Contract)
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .filter(models.Contract.settlement_date.isnot(None))
        .filter(models.Contract.settlement_date == today)
        .all()
    )

    for c in contracts:
        cp_name = c.counterparty.name if c.counterparty else "Contraparte"

        hedge_id = None
        mtm_today = _contract_mtm_today_usd(db, c, today)
        # On settlement day, liquidation value must use the FINAL monthly average (not the realized MTM proxy).
        settlement_val = None
        final_val = compute_settlement_value_for_contract_avg(db, c)
        if final_val is not None:
            settlement_val = float(final_val.mtm_usd)
        rfq = db.get(models.Rfq, c.rfq_id)
        if rfq and rfq.hedge_id:
            hedge = db.get(models.Hedge, rfq.hedge_id)
            if hedge:
                hedge_id = hedge.id
                # Fallback to legacy hedge-based values only if contract MTM couldn't be computed.
                if mtm_today is None:
                    mtm_today = hedge.mtm_value
                if settlement_val is None:
                    settlement_val = _fallback_settlement_value_from_hedge(hedge)

        out.append(
            SettlementItemRead(
                contract_id=c.contract_id,
                hedge_id=hedge_id,
                counterparty_id=c.counterparty_id,
                counterparty_name=cp_name,
                settlement_date=c.settlement_date,
                mtm_today_usd=mtm_today,
                settlement_value_usd=settlement_val,
            )
        )
    return out


@router.get(
    "/upcoming",
    response_model=List[SettlementItemRead],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def get_upcoming(
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    today = date.today()
    items: List[SettlementItemRead] = []

    contracts = (
        db.query(models.Contract)
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .filter(models.Contract.settlement_date.isnot(None))
        .filter(models.Contract.settlement_date >= today)
        .order_by(models.Contract.settlement_date.asc())
        .limit(limit)
        .all()
    )

    for c in contracts:
        cp_name = c.counterparty.name if c.counterparty else "Contraparte"

        hedge_id = None
        mtm_today = _contract_mtm_today_usd(db, c, today)
        settlement_val = None
        rfq = db.get(models.Rfq, c.rfq_id)
        if rfq and rfq.hedge_id:
            hedge = db.get(models.Hedge, rfq.hedge_id)
            if hedge:
                hedge_id = hedge.id
                if mtm_today is None:
                    mtm_today = hedge.mtm_value
                if settlement_val is None:
                    settlement_val = _fallback_settlement_value_from_hedge(hedge)

        items.append(
            SettlementItemRead(
                contract_id=c.contract_id,
                hedge_id=hedge_id,
                counterparty_id=c.counterparty_id,
                counterparty_name=cp_name,
                settlement_date=c.settlement_date,
                mtm_today_usd=mtm_today,
                settlement_value_usd=settlement_val,
            )
        )

    return items
