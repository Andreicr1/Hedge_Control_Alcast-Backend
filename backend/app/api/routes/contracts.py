import calendar
from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session, joinedload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import ContractDetailRead, ContractExposureLinkRead, ContractRead
from app.services import contract_mtm_service, pnl_engine

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _pt_norm(v: Any | None) -> str:
    return str(v or "").strip().lower()


def _month_bounds(month_name: str, year: int) -> tuple[Optional[date], Optional[date]]:
    m = (month_name or "").strip().lower()
    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }
    month = months.get(m)
    if not month:
        return None, None
    start = date(int(year), int(month), 1)
    last_day = calendar.monthrange(int(year), int(month))[1]
    end = date(int(year), int(month), int(last_day))
    return start, end


def _pick_fixed_and_variable(
    legs: list[dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    fixed = None
    variable = None

    # Prefer explicit FIX leg as fixed.
    for leg in legs:
        if _pt_norm(leg.get("price_type")) == "fix":
            fixed = leg
            break
    # Fallback: treat C2R as fixed if no FIX is present.
    if fixed is None:
        for leg in legs:
            if _pt_norm(leg.get("price_type")) == "c2r":
                fixed = leg
                break

    if fixed is not None:
        for leg in legs:
            if leg is not fixed:
                variable = leg
                break
    elif legs:
        # No obvious fixed leg; just take first/second.
        fixed = legs[0]
        variable = legs[1] if len(legs) > 1 else None
    return fixed, variable


def _variable_reference_info(leg: dict[str, Any] | None) -> tuple[Optional[str], Optional[str]]:
    if not leg:
        return None, None
    pt = _pt_norm(leg.get("price_type"))
    if pt == "avg":
        return "avg", "Média Mensal"
    if pt in {"avginter", "avg_inter", "avg inter"}:
        return "avg_inter", "Média de dias intermediários"
    if pt == "c2r":
        return "c2r", "Preço Futuro"
    return "unknown", None


def _compute_post_maturity_status(c: models.Contract, today: date) -> str:
    s = (getattr(c, "status", None) or "").strip().lower()
    if s == models.ContractStatus.settled.value:
        return "settled"
    if s == models.ContractStatus.cancelled.value:
        return "cancelled"
    if c.settlement_date and c.settlement_date < today:
        return "vencido"
    return "active"


def _settlement_adjustment_usd(
    db: Session,
    c: models.Contract,
    today: date,
) -> tuple[Optional[float], Optional[str], bool]:
    """Returns (value_usd, methodology, locked)."""
    if (getattr(c, "status", None) or "").strip().lower() == models.ContractStatus.settled.value:
        row = (
            db.query(models.PnlContractRealized)
            .filter(models.PnlContractRealized.contract_id == str(c.contract_id))
            .order_by(models.PnlContractRealized.locked_at.desc().nullslast())
            .first()
        )
        if row is not None:
            return float(row.realized_pnl_usd), row.methodology, bool(row.locked_at)
        res = pnl_engine.compute_realized_pnl_for_contract(db, c)
        if res is not None:
            return float(res.realized_pnl_usd), str(res.methodology), True
        return None, None, False

    # Active contract: expose the final settlement value once available (post-maturity).
    if c.settlement_date and c.settlement_date <= today:
        res = contract_mtm_service.compute_settlement_value_for_contract_avg(db, c)
        if res is not None:
            return float(res.mtm_usd), str(res.methodology), False

    return None, None, False


@router.get("", response_model=List[ContractRead])
def list_contracts(
    rfq_id: int | None = None,
    deal_id: int | None = None,
    q: str | None = Query(None, min_length=1, max_length=120),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    query = db.query(models.Contract)
    if rfq_id:
        query = query.filter(models.Contract.rfq_id == rfq_id)
    if deal_id:
        query = query.filter(models.Contract.deal_id == deal_id)

    if q:
        q_str = q.strip()
        if q_str:
            q_like = f"%{q_str}%"
            q_prefix = f"{q_str}%"
            filters = [
                models.Contract.contract_number.ilike(q_prefix),
                models.Contract.contract_id.ilike(q_prefix),
                models.Contract.status.ilike(q_prefix),
                models.Contract.quote_group_id.ilike(q_like),
                cast(models.Contract.deal_id, String).ilike(q_prefix),
                cast(models.Contract.rfq_id, String).ilike(q_prefix),
            ]

            if q_str.isdigit():
                q_int = int(q_str)
                filters.extend([models.Contract.deal_id == q_int, models.Contract.rfq_id == q_int])

            query = query.filter(or_(*filters))

    return query.order_by(models.Contract.created_at.desc()).limit(limit).all()


@router.get("/{contract_id}", response_model=ContractDetailRead)
def get_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    contract = (
        db.query(models.Contract)
        .options(joinedload(models.Contract.counterparty))
        .filter(models.Contract.contract_id == str(contract_id))
        .first()
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    rfq = db.get(models.Rfq, int(contract.rfq_id))
    spec = None
    idx = int(getattr(contract, "trade_index", None) or 0)
    if (
        rfq is not None
        and isinstance(getattr(rfq, "trade_specs", None), list)
        and idx < len(rfq.trade_specs)
    ):
        spec = rfq.trade_specs[idx]

    side_spec: dict[str, dict[str, Any]] = {}
    if isinstance(spec, dict):
        for k in ("leg1", "leg2"):
            leg_spec = (spec.get(k) or {}) if isinstance(spec.get(k), dict) else None
            if leg_spec and leg_spec.get("side"):
                side_spec[str(leg_spec.get("side")).strip().lower()] = leg_spec

    raw_legs = (contract.trade_snapshot or {}).get("legs") or []
    if not isinstance(raw_legs, list):
        raw_legs = []

    enriched_legs: list[dict[str, Any]] = []
    for leg in raw_legs:
        if not isinstance(leg, dict):
            continue
        side = str(leg.get("side") or "").strip().lower()
        leg_spec = side_spec.get(side) or {}

        # Quantity: prefer snapshot volume, then spec quantity, then RFQ quantity.
        qty = leg.get("volume_mt")
        if qty is None:
            qty = leg_spec.get("quantity_mt")
        if qty is None and rfq is not None:
            qty = getattr(rfq, "quantity_mt", None)

        out_leg: dict[str, Any] = {
            "side": side,
            "quantity_mt": float(qty or 0.0),
            "price_type": leg.get("price_type") or leg_spec.get("price_type"),
            "price": float(leg.get("price")) if leg.get("price") is not None else None,
            "valid_until": leg.get("valid_until"),
            "notes": leg.get("notes"),
            "month_name": leg_spec.get("month_name"),
            "year": leg_spec.get("year"),
            "start_date": leg_spec.get("start_date"),
            "end_date": leg_spec.get("end_date"),
            "fixing_date": leg_spec.get("fixing_date"),
        }
        enriched_legs.append(out_leg)

    fixed_raw, variable_raw = _pick_fixed_and_variable(enriched_legs)
    fixed_price = None
    if fixed_raw and fixed_raw.get("price") is not None:
        fixed_price = float(fixed_raw.get("price"))

    var_type, var_label = _variable_reference_info(variable_raw)

    observation_start = None
    observation_end = None
    maturity_date = None
    if variable_raw:
        pt = _pt_norm(variable_raw.get("price_type"))
        if pt == "avg":
            mn = variable_raw.get("month_name")
            yr = variable_raw.get("year")
            if mn and yr is not None:
                observation_start, observation_end = _month_bounds(str(mn), int(yr))
                maturity_date = observation_end
        elif pt in {"avginter", "avg_inter", "avg inter"}:
            observation_start = variable_raw.get("start_date")
            observation_end = variable_raw.get("end_date")
            maturity_date = observation_end
        elif pt == "c2r":
            maturity_date = variable_raw.get("fixing_date")

    today = date.today()
    post_status = _compute_post_maturity_status(contract, today)
    adj, adj_method, adj_locked = _settlement_adjustment_usd(db, contract, today)

    counterparty_name = contract.counterparty.name if contract.counterparty else None
    counterparty = (
        {"id": int(contract.counterparty.id), "name": str(contract.counterparty.name)}
        if contract.counterparty
        else None
    )

    return ContractDetailRead(
        contract_id=str(contract.contract_id),
        contract_number=contract.contract_number,
        deal_id=int(contract.deal_id),
        rfq_id=int(contract.rfq_id),
        counterparty_id=int(contract.counterparty_id)
        if contract.counterparty_id is not None
        else None,
        counterparty_name=counterparty_name,
        counterparty=counterparty,
        status=str(contract.status),
        trade_index=int(contract.trade_index) if contract.trade_index is not None else None,
        quote_group_id=contract.quote_group_id,
        trade_snapshot=contract.trade_snapshot or {},
        legs=enriched_legs,
        fixed_leg=fixed_raw,
        variable_leg=variable_raw,
        fixed_price=fixed_price,
        variable_reference_type=var_type,
        variable_reference_label=var_label,
        observation_start=observation_start,
        observation_end=observation_end,
        maturity_date=maturity_date,
        settlement_date=contract.settlement_date,
        settlement_meta=contract.settlement_meta,
        post_maturity_status=post_status,
        settlement_adjustment_usd=adj,
        settlement_adjustment_methodology=adj_method,
        settlement_adjustment_locked=bool(adj_locked),
        created_at=contract.created_at,
    )


@router.get("/{contract_id}/exposures", response_model=list[ContractExposureLinkRead])
def list_contract_exposures(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    # Validate contract exists (friendlier 404 than empty list for typos)
    if db.get(models.Contract, str(contract_id)) is None:
        raise HTTPException(status_code=404, detail="Contract not found")

    rows = (
        db.query(models.ContractExposure, models.Exposure)
        .join(models.Exposure, models.Exposure.id == models.ContractExposure.exposure_id)
        .filter(models.ContractExposure.contract_id == str(contract_id))
        .order_by(models.ContractExposure.id.asc())
        .all()
    )

    out: list[ContractExposureLinkRead] = []
    for link, exp in rows:
        out.append(
            ContractExposureLinkRead(
                exposure_id=int(exp.id),
                quantity_mt=float(link.quantity_mt),
                source_type=exp.source_type,
                source_id=int(exp.source_id),
                exposure_type=exp.exposure_type,
                status=exp.status,
            )
        )
    return out
