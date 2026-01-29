from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.deals import DealCreate, DealPnlResponse, DealRead, DealUpdate
from app.services.deal_engine import calculate_deal_pnl

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_model=list[DealRead])
def list_deals(
    q: str | None = Query(None, min_length=1, max_length=120),
    company: str | None = Query(None, min_length=1, max_length=64),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(
            models.RoleName.admin,
            models.RoleName.comercial,
            models.RoleName.financeiro,
            models.RoleName.auditoria,
        )
    ),
):
    query = db.query(models.Deal)

    if company:
        query = query.filter(models.Deal.company == company.strip())

    if q:
        q_str = q.strip()
        if q_str:
            q_like = f"%{q_str}%"
            q_prefix = f"{q_str}%"
            filters = [
                models.Deal.deal_uuid.ilike(q_prefix),
                models.Deal.reference_name.ilike(q_like),
                models.Deal.commodity.ilike(q_like),
                models.Deal.company.ilike(q_like),
                models.Deal.economic_period.ilike(q_like),
                cast(models.Deal.commercial_status, String).ilike(q_prefix),
                models.Deal.currency.ilike(q_prefix),
                cast(models.Deal.id, String).ilike(q_prefix),
                cast(models.Deal.status, String).ilike(q_prefix),
                cast(models.Deal.lifecycle_status, String).ilike(q_prefix),
            ]
            query = query.filter(or_(*filters))

    return query.order_by(models.Deal.id.desc()).limit(limit).all()


@router.get("/{deal_id}", response_model=DealRead)
def get_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(
            models.RoleName.admin,
            models.RoleName.comercial,
            models.RoleName.financeiro,
            models.RoleName.auditoria,
        )
    ),
):
    deal = db.get(models.Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.post("", response_model=DealRead, status_code=201)
def create_deal(
    payload: DealCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    currency = (payload.currency or "USD").strip().upper() or "USD"
    if len(currency) > 8:
        raise HTTPException(status_code=400, detail="Invalid currency")

    reference_name = (payload.reference_name or "").strip() or None
    commodity = (payload.commodity or "").strip() or None
    company = (payload.company or "").strip() or None
    economic_period = (payload.economic_period or "").strip() or None

    deal = models.Deal(
        reference_name=reference_name,
        commodity=commodity,
        company=company,
        economic_period=economic_period,
        commercial_status=payload.commercial_status or models.DealCommercialStatus.active,
        currency=currency,
        status=models.DealStatus.open,
        lifecycle_status=models.DealLifecycleStatus.open,
        created_by=getattr(current_user, "id", None),
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


@router.patch("/{deal_id}", response_model=DealRead)
def update_deal(
    deal_id: int,
    payload: DealUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    deal = db.get(models.Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if payload.reference_name is not None:
        cleaned = payload.reference_name.strip()
        deal.reference_name = cleaned or None

    if payload.company is not None:
        deal.company = payload.company.strip() or None

    if payload.economic_period is not None:
        deal.economic_period = payload.economic_period.strip() or None

    if payload.commercial_status is not None:
        deal.commercial_status = payload.commercial_status

    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


@router.get("/{deal_id}/pnl", response_model=DealPnlResponse)
def get_deal_pnl(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(
            models.RoleName.admin,
            models.RoleName.comercial,
            models.RoleName.financeiro,
            models.RoleName.auditoria,
        )
    ),
):
    try:
        result = calculate_deal_pnl(db, deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Deal not found")
    db.commit()
    return result
