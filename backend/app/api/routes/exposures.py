from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    exposures: list[models.Exposure] = (
        db.query(models.Exposure)
        .options(
            selectinload(models.Exposure.tasks),
            selectinload(models.Exposure.sales_order),
            selectinload(models.Exposure.purchase_order),
            selectinload(models.Exposure.hedge_links).selectinload(models.HedgeExposure.hedge).selectinload(models.Hedge.counterparty),
        )
        .order_by(models.Exposure.created_at.desc())
        .all()
    )

    for exp in exposures:
        source = getattr(exp, "sales_order", None) or getattr(exp, "purchase_order", None)
        exp.pricing_reference = _build_pricing_reference(source)

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
                    "counterparty_name": getattr(counterparty, "name", None) if counterparty else None,
                    "instrument": getattr(hedge, "instrument", None) if hedge else None,
                    "period": getattr(hedge, "period", None) if hedge else None,
                }
            )

        exp.hedged_quantity_mt = hedged_qty if links else 0.0
        try:
            total = float(getattr(exp, "quantity_mt", 0.0) or 0.0)
        except Exception:
            total = 0.0
        exp.unhedged_quantity_mt = max(total - float(exp.hedged_quantity_mt or 0.0), 0.0)
        exp.hedges = hedges_out

    return exposures
