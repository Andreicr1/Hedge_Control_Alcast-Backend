from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.schemas.cashflow_ledger import CashflowLedgerLineRead
from app.services.lme_price_service import latest_lme_price_prefer_types

_DEFAULT_OFFICIAL_SYMBOL = "Q7Y00"


def _as_utc_day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(0, 0, 0), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


@dataclass(frozen=True)
class _OfficialPricePick:
    symbol: str
    price: float
    price_type: str
    ts_price_date: date


def _latest_official_price(
    db: Session,
    *,
    symbol: str,
    as_of: date,
) -> _OfficialPricePick:
    row = latest_lme_price_prefer_types(
        db,
        symbol=symbol,
        as_of=as_of,
        price_types=["official"],
        market="LME",
    )
    if row is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "lme_official_missing",
                "message": "Missing last official LME price required for MTM projection.",
                "symbol": symbol,
                "as_of": as_of.isoformat(),
            },
        )

    return _OfficialPricePick(
        symbol=str(row.symbol),
        price=float(row.price),
        price_type=str(row.price_type),
        ts_price_date=row.ts_price.date(),
    )


def _safe_date_for_order(
    *, expected_delivery_date: date | None, fixing_deadline: date | None
) -> date:
    if expected_delivery_date is not None:
        return expected_delivery_date
    if fixing_deadline is not None:
        return fixing_deadline
    raise HTTPException(
        status_code=422,
        detail={
            "code": "missing_cashflow_date",
            "message": "Order is missing expected_delivery_date (and fixing_deadline); cannot place cashflow on a date axis.",
        },
    )


def _in_range(d: date, start: date | None, end: date | None) -> bool:
    if start is not None and d < start:
        return False
    if end is not None and d > end:
        return False
    return True


def _deal_uuid_by_id(db: Session, deal_ids: set[int]) -> dict[int, str]:
    if not deal_ids:
        return {}
    out: dict[int, str] = {}
    for d in db.query(models.Deal).filter(models.Deal.id.in_(sorted(deal_ids))).all():
        if getattr(d, "deal_uuid", None) is not None:
            out[int(d.id)] = str(d.deal_uuid)
    return out


def build_cashflow_ledger_lines(
    db: Session,
    *,
    as_of: date,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    deal_id: Optional[int] = None,
    lme_official_symbol: str = _DEFAULT_OFFICIAL_SYMBOL,
) -> list[CashflowLedgerLineRead]:
    as_of_ts = datetime.now(timezone.utc)
    valuation_ref = as_of - timedelta(days=1)

    official = _latest_official_price(db, symbol=lme_official_symbol, as_of=valuation_ref)

    rows: list[CashflowLedgerLineRead] = []
    deal_ids: set[int] = set()

    # ---- SO (physical) ----
    so_q = db.query(models.SalesOrder)
    if deal_id is not None:
        so_q = so_q.filter(models.SalesOrder.deal_id == int(deal_id))
    if start_date is not None:
        so_q = so_q.filter(
            or_(
                models.SalesOrder.expected_delivery_date >= start_date,
                models.SalesOrder.fixing_deadline >= start_date,
            )
        )
    if end_date is not None:
        so_q = so_q.filter(
            or_(
                models.SalesOrder.expected_delivery_date <= end_date,
                models.SalesOrder.fixing_deadline <= end_date,
            )
        )

    for so in so_q.order_by(models.SalesOrder.id.asc()).all():
        cf_date = _safe_date_for_order(
            expected_delivery_date=so.expected_delivery_date,
            fixing_deadline=so.fixing_deadline,
        )
        if not _in_range(cf_date, start_date, end_date):
            continue

        qty = float(so.total_quantity_mt or 0.0)
        pt = so.pricing_type
        pt_str = pt.value if hasattr(pt, "value") else str(pt)

        premium_total = float((so.lme_premium or 0.0) + (so.premium or 0.0))

        if pt == models.PriceType.FIX:
            if so.unit_price is None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "missing_fixed_price",
                        "message": "FIX SO requires unit_price.",
                        "entity": "so",
                        "so_id": int(so.id),
                    },
                )
            unit_px = float(so.unit_price)
            notes = "SO FIX: qty × unit_price"
            lme_symbol = None
            lme_pt = None
            lme_ts_date = None
        else:
            unit_px = float(official.price)
            notes = "SO variable: qty × last LME official price (projection)"
            lme_symbol = official.symbol
            lme_pt = official.price_type
            lme_ts_date = official.ts_price_date

        signed = float(qty * unit_px)
        deal_ids.add(int(so.deal_id))

        rows.append(
            CashflowLedgerLineRead(
                valuation_as_of_date=as_of,
                valuation_reference_date=valuation_ref,
                as_of=as_of_ts,
                deal_id=int(so.deal_id),
                deal_uuid=None,
                entity_type="so",
                entity_id=str(so.id),
                source_reference=str(so.so_number),
                category="physical",
                date=cf_date,
                side="sell",
                price_type=pt_str,
                quantity_mt=qty,
                unit_price_used=unit_px,
                premium_usd_per_mt=premium_total,
                amount_usd=signed,
                amount_usd_abs=abs(signed),
                direction="inflow",
                lme_symbol_used=lme_symbol,
                lme_price_type=lme_pt,
                lme_price_ts_date=lme_ts_date,
                notes=notes,
            )
        )

    # ---- PO (physical) ----
    po_q = db.query(models.PurchaseOrder)
    if deal_id is not None:
        po_q = po_q.filter(models.PurchaseOrder.deal_id == int(deal_id))
    if start_date is not None:
        po_q = po_q.filter(
            or_(
                models.PurchaseOrder.expected_delivery_date >= start_date,
                models.PurchaseOrder.fixing_deadline >= start_date,
            )
        )
    if end_date is not None:
        po_q = po_q.filter(
            or_(
                models.PurchaseOrder.expected_delivery_date <= end_date,
                models.PurchaseOrder.fixing_deadline <= end_date,
            )
        )

    for po in po_q.order_by(models.PurchaseOrder.id.asc()).all():
        cf_date = _safe_date_for_order(
            expected_delivery_date=po.expected_delivery_date,
            fixing_deadline=po.fixing_deadline,
        )
        if not _in_range(cf_date, start_date, end_date):
            continue

        qty = float(po.total_quantity_mt or 0.0)
        pt = po.pricing_type
        pt_str = pt.value if hasattr(pt, "value") else str(pt)

        premium_total = float((po.lme_premium or 0.0) + (po.premium or 0.0))

        if pt == models.PriceType.FIX:
            if po.unit_price is None:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "missing_fixed_price",
                        "message": "FIX PO requires unit_price.",
                        "entity": "po",
                        "po_id": int(po.id),
                    },
                )
            unit_px = float(po.unit_price)
            notes = "PO FIX: qty × unit_price"
            lme_symbol = None
            lme_pt = None
            lme_ts_date = None
        else:
            unit_px = float(official.price)
            notes = "PO variable: qty × last LME official price (projection)"
            lme_symbol = official.symbol
            lme_pt = official.price_type
            lme_ts_date = official.ts_price_date

        signed = float(-qty * unit_px)
        deal_ids.add(int(po.deal_id))

        rows.append(
            CashflowLedgerLineRead(
                valuation_as_of_date=as_of,
                valuation_reference_date=valuation_ref,
                as_of=as_of_ts,
                deal_id=int(po.deal_id),
                deal_uuid=None,
                entity_type="po",
                entity_id=str(po.id),
                source_reference=str(po.po_number),
                category="physical",
                date=cf_date,
                side="buy",
                price_type=pt_str,
                quantity_mt=qty,
                unit_price_used=unit_px,
                premium_usd_per_mt=premium_total,
                amount_usd=signed,
                amount_usd_abs=abs(signed),
                direction="outflow",
                lme_symbol_used=lme_symbol,
                lme_price_type=lme_pt,
                lme_price_ts_date=lme_ts_date,
                notes=notes,
            )
        )

    # ---- Contract legs (financial) ----
    c_q = (
        db.query(models.Contract)
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .filter(models.Contract.settlement_date.isnot(None))
    )
    if deal_id is not None:
        c_q = c_q.filter(models.Contract.deal_id == int(deal_id))
    if start_date is not None:
        c_q = c_q.filter(models.Contract.settlement_date >= start_date)
    if end_date is not None:
        c_q = c_q.filter(models.Contract.settlement_date <= end_date)

    for c in c_q.order_by(
        models.Contract.settlement_date.asc(), models.Contract.contract_id.asc()
    ).all():
        if c.settlement_date is None:
            continue
        if not _in_range(c.settlement_date, start_date, end_date):
            continue

        raw_legs = (c.trade_snapshot or {}).get("legs") or []
        if not isinstance(raw_legs, list):
            raw_legs = []

        rfq: models.Rfq | None = db.get(models.Rfq, int(c.rfq_id))
        rfq_qty = float(getattr(rfq, "quantity_mt", 0.0) or 0.0) if rfq is not None else 0.0

        for idx, leg in enumerate(raw_legs):
            if not isinstance(leg, dict):
                continue
            side = str(leg.get("side") or "").strip().lower()
            if side not in {"buy", "sell"}:
                continue

            qty_val = leg.get("volume_mt")
            qty = float(qty_val) if qty_val is not None else float(rfq_qty)

            pt_raw = str(leg.get("price_type") or "").strip()
            pt_norm = pt_raw.lower()

            fixed_px = None
            if pt_norm in {"fix", "c2r"} and leg.get("price") is not None:
                try:
                    fixed_px = float(leg.get("price"))
                except Exception:
                    fixed_px = None

            if fixed_px is not None:
                unit_px = float(fixed_px)
                notes = f"Contract leg FIX ({pt_raw}): qty × leg.price"
                lme_symbol = None
                lme_pt = None
                lme_ts_date = None
            else:
                unit_px = float(official.price)
                notes = "Contract leg variable: qty × last LME official price (projection)"
                lme_symbol = official.symbol
                lme_pt = official.price_type
                lme_ts_date = official.ts_price_date

            signed = float(qty * unit_px * (1.0 if side == "sell" else -1.0))
            deal_ids.add(int(c.deal_id))

            rows.append(
                CashflowLedgerLineRead(
                    valuation_as_of_date=as_of,
                    valuation_reference_date=valuation_ref,
                    as_of=as_of_ts,
                    deal_id=int(c.deal_id),
                    deal_uuid=None,
                    entity_type="contract_leg",
                    entity_id=f"{c.contract_id}:{side}:{idx}",
                    source_reference=f"contract:{c.contract_id}",
                    category="financial",
                    date=c.settlement_date,
                    side=side,  # type: ignore[arg-type]
                    price_type=pt_raw or None,
                    quantity_mt=qty,
                    unit_price_used=unit_px,
                    premium_usd_per_mt=None,
                    amount_usd=signed,
                    amount_usd_abs=abs(signed),
                    direction="inflow" if signed >= 0 else "outflow",
                    lme_symbol_used=lme_symbol,
                    lme_price_type=lme_pt,
                    lme_price_ts_date=lme_ts_date,
                    notes=notes,
                )
            )

    deal_uuid_map = _deal_uuid_by_id(db, deal_ids)
    for r in rows:
        if r.deal_id is not None and r.deal_uuid is None:
            r.deal_uuid = deal_uuid_map.get(int(r.deal_id))

    rows.sort(key=lambda x: (x.date, x.category, x.entity_type, x.entity_id))
    return rows
