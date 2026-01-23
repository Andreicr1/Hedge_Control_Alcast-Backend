"""Dashboard API routes.

This module backs the integrated frontend dashboard.
The contract is intentionally JSON-shape-compatible with the existing
frontend types in `DashboardSummary`.
"""

from __future__ import annotations

import os
import logging
import time
from copy import deepcopy
from datetime import date, datetime
from threading import Lock
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app import models
from app.api.deps import get_db, require_roles
from app.models.domain import RoleName, TimelineEvent
from app.services.contract_mtm_service import (
    compute_settlement_value_for_contract_avg,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger("alcast.dashboard")

_DASHBOARD_CACHE_ENABLED = str(os.getenv("DASHBOARD_CACHE_ENABLED", "true")).lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
_DASHBOARD_CACHE_TTL_SECONDS = 10
_DASHBOARD_CACHE_LOCK = Lock()
_DASHBOARD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DASHBOARD_CACHE_LOCKS: dict[str, Lock] = {}


def _dashboard_cache_key(current_user: models.User) -> str:
    role = None
    if current_user.role and current_user.role.name is not None:
        role = (
            current_user.role.name.value
            if hasattr(current_user.role.name, "value")
            else str(current_user.role.name)
        )
    user_id = getattr(current_user, "id", None)
    as_of = datetime.utcnow().date().isoformat()
    include_settlements = "true"
    return f"dashboard:summary:{role}:{user_id}:{as_of}:{include_settlements}"


def _dashboard_cache_get(cache_key: str) -> tuple[dict[str, Any] | None, int, bool]:
    now = time.monotonic()
    with _DASHBOARD_CACHE_LOCK:
        cached = _DASHBOARD_CACHE.get(cache_key)
        if not cached:
            return None, 0, False
        expires_at, payload = cached
        if expires_at <= now:
            remaining_ms = 0
            return deepcopy(payload), remaining_ms, True
        remaining_ms = max(0, int((expires_at - now) * 1000))
        return deepcopy(payload), remaining_ms, False


def _dashboard_cache_set(cache_key: str, payload: dict[str, Any]) -> None:
    expires_at = time.monotonic() + _DASHBOARD_CACHE_TTL_SECONDS
    with _DASHBOARD_CACHE_LOCK:
        _DASHBOARD_CACHE[cache_key] = (expires_at, deepcopy(payload))


def _dashboard_cache_lock_for_key(cache_key: str) -> Lock:
    with _DASHBOARD_CACHE_LOCK:
        lock = _DASHBOARD_CACHE_LOCKS.get(cache_key)
        if lock is None:
            lock = Lock()
            _DASHBOARD_CACHE_LOCKS[cache_key] = lock
        return lock


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
    # IMPORTANT: Dashboard requests must be fast and must not materialize MTM on-demand.
    # MTM can be expensive (reads LME price series); use snapshots only.

    def _snapshot_portfolio_total(day: date) -> tuple[float, int]:
        """Return (total_mtm_usd, rows_count) from snapshot table for the given day."""
        q = (
            db.query(models.MtmContractSnapshot)
            .join(
                models.Contract,
                models.Contract.contract_id == models.MtmContractSnapshot.contract_id,
            )
            .filter(models.MtmContractSnapshot.as_of_date == day)
            .filter(models.MtmContractSnapshot.currency == "USD")
            .filter(models.Contract.status == models.ContractStatus.active.value)
        )

        total = float(
            q.with_entities(
                func.coalesce(func.sum(models.MtmContractSnapshot.mtm_usd), 0.0)
            ).scalar()
            or 0.0
        )
        count = int(q.with_entities(func.count(models.MtmContractSnapshot.id)).scalar() or 0)
        return total, count

    def _latest_snapshot_day() -> date | None:
        try:
            return db.query(func.max(models.MtmContractSnapshot.as_of_date)).scalar()
        except Exception:
            return None

    def _portfolio_total_for_day(day: date) -> tuple[float | None, int]:
        try:
            total, count = _snapshot_portfolio_total(day)
            if count > 0:
                return float(total), int(count)
        except Exception:
            pass
        return None, 0

    snapshot_as_of = today
    is_stale = False
    snapshot_missing = False

    current, count = _portfolio_total_for_day(today)
    if not count:
        latest_day = _latest_snapshot_day()
        if latest_day:
            snapshot_as_of = latest_day
            is_stale = True
            current, count = _portfolio_total_for_day(latest_day)
        else:
            snapshot_as_of = None
            is_stale = True
            snapshot_missing = True

    if snapshot_as_of:
        base_day = snapshot_as_of
        prev_day_total, _ = _portfolio_total_for_day(base_day.fromordinal(base_day.toordinal() - 1))
        weekly_prev, _ = _portfolio_total_for_day(base_day.fromordinal(base_day.toordinal() - 7))
        monthly_prev, _ = _portfolio_total_for_day(base_day.fromordinal(base_day.toordinal() - 30))
    else:
        prev_day_total = None
        weekly_prev = None
        monthly_prev = None

    if current is None:
        current = 0.0
        prev_day_total = None

    change = float(current - (prev_day_total or current))
    change_percent = _pct_change(current, prev_day_total or current)
    weekly = float(current - weekly_prev) if weekly_prev is not None else 0.0
    monthly = float(current - monthly_prev) if monthly_prev is not None else 0.0

    period_label = f"Última atualização: {_iso(datetime.utcnow())}"
    if is_stale:
        if snapshot_as_of:
            period_label = (
                f"Snapshot MTM stale ({snapshot_as_of.isoformat()}) · {_iso(datetime.utcnow())}"
            )
        else:
            period_label = f"Snapshot MTM missing · {_iso(datetime.utcnow())}"

    return {
        "value": current,
        "currency": "USD",
        "change": change,
        "changePercent": change_percent,
        "status": _status_from_value(change),
        "is_stale": bool(is_stale),
        "snapshot_missing": bool(snapshot_missing),
        "snapshot_as_of": snapshot_as_of.isoformat() if snapshot_as_of else None,
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

    contract_ids = [str(c.contract_id) for c in contracts if c.contract_id]
    baseline_by_contract: dict[str, models.CashflowBaselineItem] = {}
    if contract_ids:
        for row in (
            db.query(models.CashflowBaselineItem)
            .filter(models.CashflowBaselineItem.contract_id.in_(contract_ids))
            .filter(models.CashflowBaselineItem.as_of_date == today)
            .filter(models.CashflowBaselineItem.currency == "USD")
            .all()
        ):
            baseline_by_contract[str(row.contract_id)] = row

    total = 0.0
    breakdown_map: dict[str, float] = {}
    allow_legacy = str(os.getenv("DASHBOARD_SETTLEMENTS_ALLOW_LEGACY", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
    }

    for c in contracts:
        baseline = baseline_by_contract.get(str(c.contract_id))
        if baseline is not None and baseline.final_value_usd is not None:
            amt = float(baseline.final_value_usd)
        elif allow_legacy:
            val = compute_settlement_value_for_contract_avg(db, c)
            amt = float(val.mtm_usd) if val is not None else 0.0
        else:
            amt = 0.0
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

    # Prefer MTM snapshots (fast). Avoid per-contract MTM computation on request path.
    contract_ids: list[str] = [str(c.contract_id) for c in contracts if c.contract_id is not None]
    mtm_by_contract_id: dict[str, float] = {}
    if contract_ids:
        rows = (
            db.query(models.MtmContractSnapshot)
            .filter(models.MtmContractSnapshot.contract_id.in_(contract_ids))
            .filter(models.MtmContractSnapshot.as_of_date == today)
            .filter(models.MtmContractSnapshot.currency == "USD")
            .order_by(desc(models.MtmContractSnapshot.id))
            .all()
        )
        # Keep the newest snapshot row per contract.
        for s in rows:
            cid = str(s.contract_id)
            if cid not in mtm_by_contract_id:
                mtm_by_contract_id[cid] = float(s.mtm_usd or 0.0)

    out: list[dict[str, Any]] = []
    for c in contracts:
        rfq = c.rfq
        so = rfq.sales_order if rfq else None
        customer_name = so.customer.name if so and so.customer else "Cliente"
        product = so.product if so and so.product else "Alumínio"
        maturity = c.settlement_date.isoformat() if c.settlement_date else ""
        rate, notional = _extract_fixed_rate_and_notional(c)

        mtm = float(mtm_by_contract_id.get(str(c.contract_id), 0.0)) if c.contract_id else 0.0

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
def get_dashboard_summary(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get dashboard summary data

    Returns MTM, settlements, RFQs, contracts, and timeline
    """
    def _safe_call(label: str, func, fallback):
        try:
            return func(), False
        except Exception as exc:  # noqa: BLE001
            logger.exception("dashboard_summary_failed", extra={"section": label, "error": str(exc)})
            return fallback, True

    cache_key = _dashboard_cache_key(current_user)
    cache_lock = _dashboard_cache_lock_for_key(cache_key) if _DASHBOARD_CACHE_ENABLED else None
    cache_lock_acquired = False
    cached = None
    ttl_ms = 0
    is_stale = False
    if _DASHBOARD_CACHE_ENABLED:
        cached, ttl_ms, is_stale = _dashboard_cache_get(cache_key)
        if cached is not None and not is_stale:
            logger.info(
                "dashboard_cache",
                extra={
                    "dashboard_cache_hit": True,
                    "dashboard_cache_ttl_remaining_ms": ttl_ms,
                    "dashboard_cache_stale": False,
                    "dashboard_cache_refresh_inflight": False,
                },
            )
            return cached

        if cache_lock is not None:
            cache_lock_acquired = cache_lock.acquire(blocking=False)
            if not cache_lock_acquired:
                if cached is not None:
                    logger.info(
                        "dashboard_cache",
                        extra={
                            "dashboard_cache_hit": True,
                            "dashboard_cache_ttl_remaining_ms": 0,
                            "dashboard_cache_stale": True,
                            "dashboard_cache_refresh_inflight": True,
                        },
                    )
                    return cached
                cache_lock.acquire()
                cache_lock_acquired = True

    try:
        mtm, mtm_failed = _safe_call(
            "mtm",
            lambda: _build_mtm_widget(db),
            {
                "value": 0.0,
                "currency": "USD",
                "change": 0.0,
                "changePercent": 0.0,
                "status": "neutral",
                "is_stale": True,
                "snapshot_missing": True,
                "snapshot_as_of": None,
                "indicators": {"dailyPnL": 0.0, "weeklyPnL": 0.0, "monthlyPnL": 0.0},
                "period": f"Snapshot MTM missing · {_iso(datetime.utcnow())}",
            },
        )
        settlements, settlements_failed = _safe_call(
            "settlements",
            lambda: _build_settlements_widget(db),
            {
                "total": 0.0,
                "currency": "USD",
                "count": 0,
                "breakdown": [],
                "status": "neutral",
                "period": "Hoje",
            },
        )
        rfqs, rfqs_failed = _safe_call("rfqs", lambda: _build_dashboard_rfqs(db), [])
        contracts, contracts_failed = _safe_call(
            "contracts",
            lambda: _build_dashboard_contracts(db),
            [],
        )
        timeline, timeline_failed = _safe_call(
            "timeline",
            lambda: _build_dashboard_timeline(db, current_user=current_user),
            [],
        )

        response = {
            "mtm": mtm,
            "settlements": settlements,
            "rfqs": rfqs,
            "contracts": contracts,
            "timeline": timeline,
            "lastUpdated": _iso(datetime.utcnow()),
        }

        had_failure = any(
            [
                mtm_failed,
                settlements_failed,
                rfqs_failed,
                contracts_failed,
                timeline_failed,
            ]
        )

        if _DASHBOARD_CACHE_ENABLED:
            logger.info(
                "dashboard_cache",
                extra={
                    "dashboard_cache_hit": False,
                    "dashboard_cache_ttl_remaining_ms": 0,
                    "dashboard_cache_stale": False,
                    "dashboard_cache_refresh_inflight": False,
                },
            )
            if not had_failure:
                _dashboard_cache_set(cache_key, response)

        return response
    finally:
        if cache_lock_acquired and cache_lock is not None:
            cache_lock.release()


@router.get("/mtm")
def get_mtm_data(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get Mark-to-Market data"""
    return _build_mtm_widget(db)


@router.get("/settlements")
def get_settlements_data(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get settlements data"""
    return _build_settlements_widget(db)


@router.get("/rfqs")
def get_rfqs(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get RFQs list"""
    return _build_dashboard_rfqs(db)


@router.get("/contracts")
def get_contracts(
    current_user: models.User = Depends(
        require_roles(RoleName.admin, RoleName.financeiro, RoleName.auditoria)
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get contracts list"""
    return _build_dashboard_contracts(db)


@router.get("/timeline")
def get_timeline(
    current_user: models.User = Depends(
        require_roles(
            RoleName.admin,
            RoleName.comercial,
            RoleName.financeiro,
            RoleName.estoque,
            RoleName.auditoria,
        )
    ),
    db: Session = Depends(get_db),
) -> Any:
    """Get timeline items"""
    return _build_dashboard_timeline(db, current_user=current_user)
