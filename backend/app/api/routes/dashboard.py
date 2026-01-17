"""Dashboard API routes.

This module backs the integrated frontend dashboard.
The contract is intentionally JSON-shape-compatible with the existing
frontend types in `DashboardSummary`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app import models
from app.api.deps import get_db, require_roles
from app.models.domain import RoleName, TimelineEvent
from app.services.contract_mtm_service import (
    compute_mtm_for_contract_avg,
    compute_settlement_value_for_contract_avg,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _iso(dt: datetime | None) -> str:
    if not dt:
        return ""
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def _status_from_value(v: float) -> str:
    if v > 0:
        return "positive"
    if v < 0:
        return "negative"
    return "neutral"


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return float((current - previous) / abs(previous) * 100.0)


def _timeline_visibility_filter_for(user: models.User):
    if user.role and user.role.name == models.RoleName.admin:
        return None
    if user.role and user.role.name == models.RoleName.financeiro:
        return TimelineEvent.visibility.in_(["all", "finance"])
    if user.role and user.role.name == models.RoleName.auditoria:
        return TimelineEvent.visibility.in_(["all", "finance"])
    return TimelineEvent.visibility == "all"


def _build_mtm_widget(db: Session) -> dict[str, Any]:
    """Compute a portfolio MTM widget from active contracts.

    Notes:
    - Uses the existing contract MTM service; contracts without computable MTM are skipped.
    - Values are in USD today (no FX conversion here).
    """

    today = date.today()
    contracts = (
        db.query(models.Contract)
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .all()
    )

    def _sum_for_day(day: date) -> float:
        total = 0.0
        for c in contracts:
            res = compute_mtm_for_contract_avg(db, c, as_of_date=day)
            if res is None:
                continue
            total += float(res.mtm_usd)
        return float(total)

    current = _sum_for_day(today)
    prev_day = _sum_for_day(today.replace(day=today.day) if False else (today))
    # Compute a true previous day value when possible.
    try:
        prev_day = _sum_for_day(today.fromordinal(today.toordinal() - 1))
    except Exception:
        prev_day = current

    change = float(current - prev_day)
    change_percent = _pct_change(current, prev_day)

    # Lightweight indicators; computed from the same MTM logic.
    weekly = current
    monthly = current
    try:
        weekly_prev = _sum_for_day(today.fromordinal(today.toordinal() - 7))
        weekly = float(current - weekly_prev)
    except Exception:
        weekly = 0.0
    try:
        monthly_prev = _sum_for_day(today.fromordinal(today.toordinal() - 30))
        monthly = float(current - monthly_prev)
    except Exception:
        monthly = 0.0

    period_label = (
        f"Última atualização: {_iso(datetime.utcnow())}" if contracts else "Sem contratos ativos"
    )

    return {
        "value": current,
        "currency": "USD",
        "change": change,
        "changePercent": change_percent,
        "status": _status_from_value(change),
        "indicators": {
            "dailyPnL": change,
            "weeklyPnL": weekly,
            "monthlyPnL": monthly,
        },
        "period": period_label,
    }


def _build_settlements_widget(db: Session) -> dict[str, Any]:
    today = date.today()
    contracts = (
        db.query(models.Contract)
        .options(joinedload(models.Contract.counterparty))
        .filter(models.Contract.status == models.ContractStatus.active.value)
        .filter(models.Contract.settlement_date.isnot(None))
        .filter(models.Contract.settlement_date == today)
        .all()
    )

    total = 0.0
    breakdown_map: dict[str, float] = {}
    for c in contracts:
        val = compute_settlement_value_for_contract_avg(db, c)
        amt = float(val.mtm_usd) if val is not None else 0.0
        total += amt
        label = c.counterparty.name if c.counterparty else "Contraparte"
        breakdown_map[label] = float(breakdown_map.get(label, 0.0) + amt)

    breakdown = [
        {"label": k, "value": v} for k, v in sorted(breakdown_map.items(), key=lambda kv: kv[0])
    ]

    return {
        "total": float(total),
        "currency": "USD",
        "count": int(len(contracts)),
        "breakdown": breakdown,
        "status": "success" if contracts else "neutral",
        "period": "Hoje",
    }


def _build_dashboard_rfqs(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    rfqs = (
        db.query(models.Rfq)
        .options(joinedload(models.Rfq.sales_order).joinedload(models.SalesOrder.customer))
        .order_by(desc(models.Rfq.created_at))
        .limit(limit)
        .all()
    )

    out: list[dict[str, Any]] = []
    for r in rfqs:
        so = r.sales_order
        customer_name = so.customer.name if so and so.customer else "Cliente"
        product = so.product if so and so.product else "Alumínio"
        maturity = (
            so.expected_delivery_date.isoformat()
            if so and so.expected_delivery_date
            else (r.period or "")
        )
        out.append(
            {
                "id": str(r.id),
                "client": customer_name,
                "product": product,
                "amount": float(r.quantity_mt or 0.0),
                "currency": "USD",
                "maturity": maturity,
                "status": (r.status.value if hasattr(r.status, "value") else str(r.status)),
                "priority": "high" if (r.status == models.RfqStatus.pending) else "medium",
                "timestamp": _iso(r.created_at),
            }
        )
    return out


def _extract_fixed_rate_and_notional(contract: models.Contract) -> tuple[float, float]:
    """Return (rate, notional) from the stored trade snapshot when possible."""
    snapshot = contract.trade_snapshot or {}
    legs = (snapshot.get("legs") or []) if isinstance(snapshot, dict) else []

    rate: float = 0.0
    notional: float = 0.0
    for leg in legs:
        try:
            if (str(leg.get("price_type") or "").strip().lower() in {"fix", "c2r"}) and rate == 0.0:
                rate = float(leg.get("price") or 0.0)
        except Exception:
            pass
        try:
            vol = leg.get("volume_mt")
            if vol is not None:
                notional = max(notional, float(vol))
        except Exception:
            pass

    return rate, notional


def _build_dashboard_contracts(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    today = date.today()
    contracts = (
        db.query(models.Contract)
        .options(
            joinedload(models.Contract.counterparty),
            joinedload(models.Contract.rfq)
            .joinedload(models.Rfq.sales_order)
            .joinedload(models.SalesOrder.customer),
        )
        .order_by(desc(models.Contract.created_at))
        .limit(limit)
        .all()
    )

    out: list[dict[str, Any]] = []
    for c in contracts:
        rfq = c.rfq
        so = rfq.sales_order if rfq else None
        customer_name = so.customer.name if so and so.customer else "Cliente"
        product = so.product if so and so.product else "Alumínio"
        maturity = c.settlement_date.isoformat() if c.settlement_date else ""
        rate, notional = _extract_fixed_rate_and_notional(c)

        mtm = 0.0
        res = compute_mtm_for_contract_avg(db, c, as_of_date=today)
        if res is not None:
            mtm = float(res.mtm_usd)

        out.append(
            {
                "id": str(c.contract_id),
                "contractNumber": str(c.contract_id),
                "client": customer_name,
                "product": product,
                "notional": float(notional or 0.0),
                "currency": "USD",
                "rate": float(rate or 0.0),
                "maturity": maturity,
                "status": str(c.status or ""),
                "mtm": mtm,
            }
        )
    return out


def _initials(name: str | None) -> str:
    parts = [p for p in (name or "").replace("  ", " ").split(" ") if p]
    if not parts:
        return "SY"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def _build_dashboard_timeline(
    db: Session,
    current_user: models.User,
    limit: int = 10,
) -> list[dict[str, Any]]:
    q = db.query(models.TimelineEvent).options(
        joinedload(models.TimelineEvent.actor).joinedload(models.User.role)
    )
    vis = _timeline_visibility_filter_for(current_user)
    if vis is not None:
        q = q.filter(vis)

    events = (
        q.order_by(desc(models.TimelineEvent.occurred_at), desc(models.TimelineEvent.id))
        .limit(limit)
        .all()
    )

    out: list[dict[str, Any]] = []
    for ev in events:
        actor_name = ev.actor.name if ev.actor else "Sistema"
        role = None
        if ev.actor and ev.actor.role:
            role = (
                ev.actor.role.name.value
                if hasattr(ev.actor.role.name, "value")
                else str(ev.actor.role.name)
            )
        out.append(
            {
                "id": str(ev.id),
                "author": actor_name,
                "role": role or "Automático",
                "timestamp": _iso(ev.occurred_at),
                "content": f"{ev.event_type} · {ev.subject_type} #{ev.subject_id}",
                "avatar": {
                    "initials": _initials(actor_name),
                    "colorScheme": (1 if ev.visibility == "finance" else 2),
                },
                "highlight": True if ev.visibility == "finance" else False,
            }
        )
    return out


@router.get("/summary")
async def get_dashboard_summary(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get dashboard summary data

    Returns MTM, settlements, RFQs, contracts, and timeline
    """
    return {
        "mtm": _build_mtm_widget(db),
        "settlements": _build_settlements_widget(db),
        "rfqs": _build_dashboard_rfqs(db),
        "contracts": _build_dashboard_contracts(db),
        "timeline": _build_dashboard_timeline(db, current_user=current_user),
        "lastUpdated": _iso(datetime.utcnow()),
    }


@router.get("/mtm")
async def get_mtm_data(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get Mark-to-Market data"""
    return _build_mtm_widget(db)


@router.get("/settlements")
async def get_settlements_data(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get settlements data"""
    return _build_settlements_widget(db)


@router.get("/rfqs")
async def get_rfqs(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get RFQs list"""
    return _build_dashboard_rfqs(db)


@router.get("/contracts")
async def get_contracts(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get contracts list"""
    return _build_dashboard_contracts(db)


@router.get("/timeline")
async def get_timeline(
    current_user: models.User = Depends(
        require_roles(
            RoleName.admin,
            RoleName.compras,
            RoleName.vendas,
            RoleName.financeiro,
            RoleName.estoque,
            RoleName.auditoria,
        )
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get timeline items"""
    return _build_dashboard_timeline(db, current_user=current_user)
