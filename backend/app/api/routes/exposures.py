from datetime import date
from typing import List
import os

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, noload, selectinload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import ExposureRead

router = APIRouter(prefix="/exposures", tags=["exposures"])


def _build_pricing_reference(source) -> str | None:
    if not source:
        return None

    ref = getattr(source, "reference_price", None)
    pricing_type = getattr(source, "pricing_type", None)
    pricing_period = getattr(source, "pricing_period", None)
    premium = getattr(source, "premium", None)
    lme_premium = getattr(source, "lme_premium", None)

    parts: list[str] = []

    if ref:
        parts.append(str(ref))
    elif pricing_type is not None:
        pv = getattr(pricing_type, "value", None) or str(pricing_type)
        parts.append(pv)

    # If it is an index-based pricing, period helps executives understand which fixing.
    if pricing_period:
        parts.append(str(pricing_period))

    has_premium = False
    try:
        has_premium = (premium is not None and float(premium) != 0.0) or (
            lme_premium is not None and float(lme_premium) != 0.0
        )
    except Exception:
        has_premium = False

    if has_premium:
        parts.append("+ Premium")

    out = " ".join([p for p in parts if p]).strip()
    return out or None


@router.get("", response_model=List[ExposureRead])
def list_exposures(
    limit: int = Query(int(os.getenv("EXPOSURES_LIST_DEFAULT_LIMIT", "50")), ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="Comma-separated exposure statuses"),
    period: str | None = Query(None, description="YYYY-MM"),
    start_date: date | None = Query(None, description="Filter delivery/payment/sale >= YYYY-MM-DD"),
    end_date: date | None = Query(None, description="Filter delivery/payment/sale <= YYYY-MM-DD"),
    expand: str | None = Query(None, description="Expand: tasks,hedges"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    """List exposures with pagination.

    Default payload excludes tasks and hedges. Use ?expand=tasks,hedges
    to include them.
    """
    max_limit = int(os.getenv("EXPOSURES_LIST_MAX_LIMIT", "200"))
    safe_limit = min(int(limit), max_limit)

    env_default_expand = os.getenv("EXPOSURES_LIST_DEFAULT_EXPAND", "")
    expand_value = ",".join([v for v in [env_default_expand, expand or ""] if v])
    expand_set = {e.strip().lower() for e in expand_value.split(",") if e.strip()}
    include_tasks = "tasks" in expand_set
    include_hedges = "hedges" in expand_set

    q = db.query(models.Exposure).options(
        noload(models.Exposure.tasks),
        noload(models.Exposure.hedge_links),
        selectinload(models.Exposure.sales_order),
        selectinload(models.Exposure.purchase_order),
    )

    if include_tasks:
        q = q.options(selectinload(models.Exposure.tasks))
    if include_hedges:
        q = q.options(
            selectinload(models.Exposure.hedge_links)
            .selectinload(models.HedgeExposure.hedge)
            .selectinload(models.Hedge.counterparty)
        )

    if status:
        raw_statuses = [s.strip().lower() for s in status.split(",") if s.strip()]
        allowed = {s.value for s in models.ExposureStatus}
        normalized = [s for s in raw_statuses if s in allowed]
        if normalized:
            q = q.filter(models.Exposure.status.in_(normalized))

    date_expr = func.coalesce(
        models.Exposure.delivery_date,
        models.Exposure.sale_date,
        models.Exposure.payment_date,
    )

    if start_date:
        q = q.filter(
            or_(
                models.Exposure.delivery_date >= start_date,
                models.Exposure.sale_date >= start_date,
                models.Exposure.payment_date >= start_date,
            )
        )
    if end_date:
        q = q.filter(
            or_(
                models.Exposure.delivery_date <= end_date,
                models.Exposure.sale_date <= end_date,
                models.Exposure.payment_date <= end_date,
            )
        )

    if period:
        dialect = db.get_bind().dialect.name if db.get_bind() is not None else ""
        if dialect == "sqlite":
            q = q.filter(func.strftime("%Y-%m", date_expr) == period)
        else:
            q = q.filter(func.to_char(date_expr, "YYYY-MM") == period)

    exposures: list[models.Exposure] = (
        q.order_by(models.Exposure.created_at.desc())
        .offset(int(offset))
        .limit(safe_limit)
        .all()
    )

    hedged_by_exposure_id: dict[int, float] = {}
    if exposures and not include_hedges:
        exp_ids = [int(e.id) for e in exposures]
        rows = (
            db.query(
                models.HedgeExposure.exposure_id,
                func.coalesce(func.sum(models.HedgeExposure.quantity_mt), 0.0),
            )
            .filter(models.HedgeExposure.exposure_id.in_(exp_ids))
            .group_by(models.HedgeExposure.exposure_id)
            .all()
        )
        for exposure_id, qty in rows:
            if exposure_id is None:
                continue
            hedged_by_exposure_id[int(exposure_id)] = float(qty or 0.0)

    for exp in exposures:
        source = getattr(exp, "sales_order", None) or getattr(exp, "purchase_order", None)
        exp.pricing_reference = _build_pricing_reference(source)

        if include_hedges:
            links = list(getattr(exp, "hedge_links", None) or [])
            hedged_qty = 0.0
            hedges_out = []
            for link in links:
                q = float(getattr(link, "quantity_mt", 0.0) or 0.0)
                hedged_qty += q

                hedge = getattr(link, "hedge", None)
                counterparty = getattr(hedge, "counterparty", None) if hedge else None
                hedges_out.append(
                    {
                        "hedge_id": int(getattr(link, "hedge_id")),
                        "quantity_mt": q,
                        "counterparty_name": getattr(counterparty, "name", None)
                        if counterparty
                        else None,
                        "instrument": getattr(hedge, "instrument", None) if hedge else None,
                        "period": getattr(hedge, "period", None) if hedge else None,
                    }
                )
            exp.hedged_quantity_mt = hedged_qty if links else 0.0
            exp.hedges = hedges_out
        else:
            exp.hedges = []
            exp.hedged_quantity_mt = float(hedged_by_exposure_id.get(int(exp.id), 0.0))
        try:
            total = float(getattr(exp, "quantity_mt", 0.0) or 0.0)
        except Exception:
            total = 0.0
        exp.unhedged_quantity_mt = max(total - float(exp.hedged_quantity_mt or 0.0), 0.0)

        if not include_tasks:
            exp.tasks = []

    return exposures
