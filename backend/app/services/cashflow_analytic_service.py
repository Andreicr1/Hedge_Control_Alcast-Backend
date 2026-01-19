from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.schemas.cashflow_analytic import CashFlowLineRead
from app.services.cashflow_service import build_cashflow_items
from app.services.exposure_engine import _hedged_quantity_mt

_DEFAULT_LME_SYMBOL = "Q7Y00"  # official
_ALLOWED_LME_SYMBOLS = {"P3Y00", "P4Y00", "Q7Y00"}


def _as_utc_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(0, 0, 0), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _resolve_lme_symbol(reference_price: str | None) -> str:
    sym = (reference_price or "").strip()
    if sym in _ALLOWED_LME_SYMBOLS:
        return sym
    return _DEFAULT_LME_SYMBOL


def _mtm_price_d_minus_1(
    db: Session,
    *,
    symbol: str,
    ref_date: date,
) -> float:
    start, end = _as_utc_day_bounds(ref_date)

    # Harmonized with LME ingestion:
    # - Q7Y00 (official) only has price_type='official'
    # - P3Y00/P4Y00 typically have price_type in {'close','live'}
    #
    # For MTM(D-1) projection we prefer close when available for cash/3M,
    # otherwise fall back to live. Keep official as a backward-compatible fallback.
    if symbol == "Q7Y00":
        priority = ["official"]
    else:
        priority = ["close", "live", "official"]

    q_base = (
        db.query(models.LMEPrice)
        .filter(models.LMEPrice.symbol == symbol)
        .filter(models.LMEPrice.ts_price >= start)
        .filter(models.LMEPrice.ts_price < end)
        .order_by(models.LMEPrice.ts_price.desc())
    )

    for pt in priority:
        row = q_base.filter(models.LMEPrice.price_type == pt).first()
        if row is not None:
            return float(row.price)

    raise HTTPException(
        status_code=422,
        detail={
            "code": "mtm_price_missing",
            "message": "Missing MTM(D-1) market data for variable pricing cashflow projection.",
            "symbol": symbol,
            "valuation_reference_date": ref_date.isoformat(),
            "price_types_tried": priority,
        },
    )


def _safe_date_for_order(*, expected_delivery_date: date | None, fixing_deadline: date | None) -> date:
    if expected_delivery_date is not None:
        return expected_delivery_date
    if fixing_deadline is not None:
        return fixing_deadline
    # No safe time axis anchor; raise rather than guessing.
    raise HTTPException(
        status_code=422,
        detail={
            "code": "missing_cashflow_date",
            "message": "Order is missing expected_delivery_date (and fixing_deadline); cannot place cashflow on a date axis.",
        },
    )


@dataclass(frozen=True)
class CashflowAnalyticFilters:
    start_date: date | None = None
    end_date: date | None = None
    deal_id: int | None = None


def build_cashflow_analytic_lines(
    db: Session,
    *,
    as_of: date,
    filters: CashflowAnalyticFilters,
) -> list[CashFlowLineRead]:
    as_of_ts = datetime.now(timezone.utc)
    valuation_ref = as_of - timedelta(days=1)

    out: list[CashFlowLineRead] = []

    # ---- SO / PO (physical) ----
    so_q = db.query(models.SalesOrder)
    po_q = db.query(models.PurchaseOrder)
    if filters.deal_id is not None:
        so_q = so_q.filter(models.SalesOrder.deal_id == int(filters.deal_id))
        po_q = po_q.filter(models.PurchaseOrder.deal_id == int(filters.deal_id))

    sales_orders = so_q.order_by(models.SalesOrder.id.asc()).all()
    purchase_orders = po_q.order_by(models.PurchaseOrder.id.asc()).all()

    def _in_range(d: date) -> bool:
        if filters.start_date is not None and d < filters.start_date:
            return False
        if filters.end_date is not None and d > filters.end_date:
            return False
        return True

    for so in sales_orders:
        cf_date = _safe_date_for_order(
            expected_delivery_date=so.expected_delivery_date,
            fixing_deadline=so.fixing_deadline,
        )
        if not _in_range(cf_date):
            continue

        qty = float(so.total_quantity_mt or 0.0)
        pt = so.pricing_type
        pt_str = pt.value if hasattr(pt, "value") else str(pt)

        if pt == models.PriceType.FIX:
            fixed_price = so.unit_price
            if fixed_price is None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "missing_fixed_price",
                        "message": "FIX order requires unit_price to compute deterministic cashflow amount.",
                        "entity": "so",
                        "so_id": int(so.id),
                    },
                )
            unit_price_used = float(fixed_price)
            amount = abs(qty * unit_price_used)
            out.append(
                CashFlowLineRead(
                    entity_type="so",
                    entity_id=str(so.id),
                    parent_id=str(so.deal_id),
                    cashflow_type="physical",
                    date=cf_date,
                    amount=float(amount),
                    price_type=pt_str,
                    valuation_method="fixed",
                    valuation_reference_date=None,
                    confidence="deterministic",
                    direction="inflow",
                    quantity_mt=qty,
                    unit_price_used=float(unit_price_used),
                    source_reference=str(so.so_number),
                    explanation="SO physical cashflow (FIX): amount = quantity_mt × unit_price. No Exposure is generated for FIX.",
                    as_of=as_of_ts,
                )
            )
        else:
            # Variable pricing: MTM(D-1) for projection only.
            symbol = _resolve_lme_symbol(so.reference_price)
            mtm_px = _mtm_price_d_minus_1(db, symbol=symbol, ref_date=valuation_ref)
            amount = abs(qty * float(mtm_px))
            out.append(
                CashFlowLineRead(
                    entity_type="so",
                    entity_id=str(so.id),
                    parent_id=str(so.deal_id),
                    cashflow_type="physical",
                    date=cf_date,
                    amount=float(amount),
                    price_type=pt_str,
                    valuation_method="mtm",
                    valuation_reference_date=valuation_ref,
                    confidence="estimated",
                    direction="inflow",
                    quantity_mt=qty,
                    unit_price_used=float(mtm_px),
                    source_reference=str(so.so_number),
                    explanation="SO physical cashflow (variable): amount = quantity_mt × MTM(D-1). MTM is used exclusively for cashflow projection (not accounting PnL).",
                    as_of=as_of_ts,
                )
            )

    for po in purchase_orders:
        cf_date = _safe_date_for_order(
            expected_delivery_date=po.expected_delivery_date,
            fixing_deadline=po.fixing_deadline,
        )
        if not _in_range(cf_date):
            continue

        qty = float(po.total_quantity_mt or 0.0)
        pt = po.pricing_type
        pt_str = pt.value if hasattr(pt, "value") else str(pt)

        if pt == models.PriceType.FIX:
            fixed_price = po.unit_price
            if fixed_price is None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "missing_fixed_price",
                        "message": "FIX order requires unit_price to compute deterministic cashflow amount.",
                        "entity": "po",
                        "po_id": int(po.id),
                    },
                )
            unit_price_used = float(fixed_price)
            amount = abs(qty * unit_price_used)
            out.append(
                CashFlowLineRead(
                    entity_type="po",
                    entity_id=str(po.id),
                    parent_id=str(po.deal_id),
                    cashflow_type="physical",
                    date=cf_date,
                    amount=float(amount),
                    price_type=pt_str,
                    valuation_method="fixed",
                    valuation_reference_date=None,
                    confidence="deterministic",
                    direction="outflow",
                    quantity_mt=qty,
                    unit_price_used=float(unit_price_used),
                    source_reference=str(po.po_number),
                    explanation="PO physical cashflow (FIX): amount = quantity_mt × unit_price. No Exposure is generated for FIX.",
                    as_of=as_of_ts,
                )
            )
        else:
            symbol = _resolve_lme_symbol(po.reference_price)
            mtm_px = _mtm_price_d_minus_1(db, symbol=symbol, ref_date=valuation_ref)
            amount = abs(qty * float(mtm_px))
            out.append(
                CashFlowLineRead(
                    entity_type="po",
                    entity_id=str(po.id),
                    parent_id=str(po.deal_id),
                    cashflow_type="physical",
                    date=cf_date,
                    amount=float(amount),
                    price_type=pt_str,
                    valuation_method="mtm",
                    valuation_reference_date=valuation_ref,
                    confidence="estimated",
                    direction="outflow",
                    quantity_mt=qty,
                    unit_price_used=float(mtm_px),
                    source_reference=str(po.po_number),
                    explanation="PO physical cashflow (variable): amount = quantity_mt × MTM(D-1). MTM is used exclusively for cashflow projection (not accounting PnL).",
                    as_of=as_of_ts,
                )
            )

    # ---- Contracts (financial) ----
    c_q = (
        db.query(models.Contract)
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .filter(models.Contract.settlement_date.isnot(None))
    )
    if filters.deal_id is not None:
        c_q = c_q.filter(models.Contract.deal_id == int(filters.deal_id))
    if filters.start_date is not None:
        c_q = c_q.filter(models.Contract.settlement_date >= filters.start_date)
    if filters.end_date is not None:
        c_q = c_q.filter(models.Contract.settlement_date <= filters.end_date)

    contracts = c_q.order_by(models.Contract.settlement_date.asc(), models.Contract.contract_id.asc()).all()
    contract_items = build_cashflow_items(db, contracts, as_of=as_of)
    for it in contract_items:
        if it.settlement_date is None:
            continue
        if not _in_range(it.settlement_date):
            continue

        val = None
        valuation_method = "mtm"
        confidence = "estimated"
        valuation_reference_date = it.projected_as_of

        if as_of >= it.settlement_date and it.final_value_usd is not None:
            val = float(it.final_value_usd)
            valuation_method = "fixed"
            confidence = "deterministic"
            valuation_reference_date = it.settlement_date
        elif it.projected_value_usd is not None:
            val = float(it.projected_value_usd)

        if val is None:
            # Keep a placeholder line to preserve visibility, but remain explicit.
            val = 0.0
            confidence = "estimated"
            valuation_method = "mtm"

        direction = "inflow" if val >= 0 else "outflow"
        amount = abs(float(val))

        out.append(
            CashFlowLineRead(
                entity_type="contract",
                entity_id=str(it.contract_id),
                parent_id=str(it.deal_id),
                cashflow_type="financial",
                date=it.settlement_date,
                amount=float(amount),
                price_type=None,
                valuation_method=valuation_method,  # type: ignore[arg-type]
                valuation_reference_date=valuation_reference_date,
                confidence=confidence,  # type: ignore[arg-type]
                direction=direction,  # type: ignore[arg-type]
                quantity_mt=None,
                unit_price_used=None,
                source_reference=f"contract:{it.contract_id}",
                explanation=(
                    "Contract financial settlement cashflow line. "
                    + ("Final (realized) value used." if valuation_method == "fixed" else "Projected value used.")
                ),
                as_of=as_of_ts,
            )
        )

    # ---- Exposures (risk) ----
    e_q = db.query(models.Exposure).filter(
        models.Exposure.status.in_([models.ExposureStatus.open, models.ExposureStatus.partially_hedged])
    )
    exposures = e_q.order_by(models.Exposure.id.asc()).all()

    # Pre-fetch related orders for price_type and deal linkage.
    so_by_id: dict[int, models.SalesOrder] = {}
    po_by_id: dict[int, models.PurchaseOrder] = {}
    if exposures:
        so_ids = [int(e.source_id) for e in exposures if e.source_type == models.MarketObjectType.so]
        po_ids = [int(e.source_id) for e in exposures if e.source_type == models.MarketObjectType.po]
        if so_ids:
            for so in db.query(models.SalesOrder).filter(models.SalesOrder.id.in_(so_ids)).all():
                so_by_id[int(so.id)] = so
        if po_ids:
            for po in db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id.in_(po_ids)).all():
                po_by_id[int(po.id)] = po

    for exp in exposures:
        # Only include exposures that represent an open or partial gap.
        hedged = _hedged_quantity_mt(db=db, exposure_id=int(exp.id))
        total = float(exp.quantity_mt or 0.0)
        gap_qty = max(0.0, total - float(hedged))
        if gap_qty <= 1e-9:
            continue

        exp_date = exp.delivery_date or exp.payment_date
        if exp_date is None:
            # Exposure without a delivery/payment date cannot be placed on a time axis.
            continue
        if not _in_range(exp_date):
            continue

        deal_id: int | None = None
        price_type: str | None = None
        symbol = _DEFAULT_LME_SYMBOL

        if exp.source_type == models.MarketObjectType.so:
            so = so_by_id.get(int(exp.source_id))
            if so is not None:
                deal_id = int(so.deal_id)
                price_type = so.pricing_type.value
                symbol = _resolve_lme_symbol(so.reference_price)
        elif exp.source_type == models.MarketObjectType.po:
            po = po_by_id.get(int(exp.source_id))
            if po is not None:
                deal_id = int(po.deal_id)
                price_type = po.pricing_type.value
                symbol = _resolve_lme_symbol(po.reference_price)

        if filters.deal_id is not None and deal_id is not None and deal_id != int(filters.deal_id):
            continue

        mtm_px = _mtm_price_d_minus_1(db, symbol=symbol, ref_date=valuation_ref)
        amount = abs(gap_qty * float(mtm_px))

        direction: str
        if exp.exposure_type == models.ExposureType.active:
            direction = "inflow"
        else:
            direction = "outflow"

        out.append(
            CashFlowLineRead(
                entity_type="exposure",
                entity_id=str(exp.id),
                parent_id=str(deal_id) if deal_id is not None else None,
                cashflow_type="risk",
                date=exp_date,
                amount=float(amount),
                price_type=price_type,
                valuation_method="mtm",
                valuation_reference_date=valuation_ref,
                confidence="risk",
                direction=direction,  # type: ignore[arg-type]
                quantity_mt=float(gap_qty),
                unit_price_used=float(mtm_px),
                source_reference=f"exposure:{exp.id}",
                explanation="Risk cashflow line representing the open/unhedged gap (Exposure open/partial). amount = gap_qty × MTM(D-1).",
                as_of=as_of_ts,
            )
        )

    # Ensure deterministic ordering: date asc, cashflow_type, entity_type, entity_id
    out.sort(key=lambda r: (r.date, r.cashflow_type, r.entity_type, r.entity_id))
    return out
