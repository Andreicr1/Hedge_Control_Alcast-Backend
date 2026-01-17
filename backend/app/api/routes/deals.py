from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.deals import DealPnlResponse, DealRead, DealUpdate
from app.services.deal_engine import calculate_deal_pnl

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_model=list[DealRead])
def list_deals(
    q: str | None = Query(None, min_length=1, max_length=120),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    query = db.query(models.Deal)

    if q:
        q_str = q.strip()
        if q_str:
            q_like = f"%{q_str}%"
            q_prefix = f"{q_str}%"
            filters = [
                models.Deal.deal_uuid.ilike(q_prefix),
                models.Deal.reference_name.ilike(q_like),
                models.Deal.commodity.ilike(q_like),
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
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    deal = db.get(models.Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.patch("/{deal_id}", response_model=DealRead)
def update_deal(
    deal_id: int,
    payload: DealUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    deal = db.get(models.Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if payload.reference_name is not None:
        cleaned = payload.reference_name.strip()
        deal.reference_name = cleaned or None

    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


@router.get("/{deal_id}/pnl", response_model=DealPnlResponse)
def get_deal_pnl(
    deal_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
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
