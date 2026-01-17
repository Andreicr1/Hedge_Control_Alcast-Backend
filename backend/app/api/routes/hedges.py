from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import HedgeCreate, HedgeRead, HedgeUpdate
from app.services.deal_engine import link_hedge_to_deal

router = APIRouter(prefix="/hedges", tags=["hedges"])


@router.get("", response_model=List[HedgeRead])
def list_hedges(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    return db.query(models.Hedge).order_by(models.Hedge.created_at.desc()).all()


@router.post("", response_model=HedgeRead, status_code=status.HTTP_201_CREATED)
def create_hedge(
    payload: HedgeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    if not db.get(models.SalesOrder, payload.so_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sales Order not found")
    if not db.get(models.Counterparty, payload.counterparty_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Counterparty not found"
        )
    if payload.deal_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="deal_id is required for hedge linking"
        )
    if payload.quantity_mt <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Quantidade deve ser positiva."
        )
    if payload.contract_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Preço de contrato deve ser positivo."
        )

    hedge = models.Hedge(
        so_id=payload.so_id,
        counterparty_id=payload.counterparty_id,
        quantity_mt=payload.quantity_mt,
        contract_price=payload.contract_price,
        current_market_price=payload.current_market_price,
        mtm_value=payload.mtm_value,
        period=payload.period,
        maturity_date=getattr(payload, "maturity_date", None),
        status=payload.status,
    )
    db.add(hedge)
    db.flush()
    try:
        link_hedge_to_deal(db, hedge, payload.deal_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    db.refresh(hedge)
    return hedge


@router.get("/{hedge_id}", response_model=HedgeRead)
def get_hedge(
    hedge_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    hedge = db.get(models.Hedge, hedge_id)
    if not hedge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hedge not found")
    return hedge


@router.put("/{hedge_id}", response_model=HedgeRead)
def update_hedge(
    hedge_id: int,
    payload: HedgeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    hedge = db.get(models.Hedge, hedge_id)
    if not hedge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hedge not found")

    data = payload.dict(exclude_unset=True)
    # deal_id is used only for linking, not a Hedge column
    deal_id = data.pop("deal_id", None)
    if "quantity_mt" in data and data["quantity_mt"] is not None and data["quantity_mt"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Quantidade deve ser positiva."
        )
    if (
        "contract_price" in data
        and data["contract_price"] is not None
        and data["contract_price"] <= 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Preço de contrato deve ser positivo."
        )
    for field, value in data.items():
        setattr(hedge, field, value)

    if deal_id is not None:
        try:
            link_hedge_to_deal(db, hedge, deal_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    db.add(hedge)
    db.commit()
    db.refresh(hedge)
    return hedge
