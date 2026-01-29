# ruff: noqa: B008, E501

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import AssignDealRequest, SalesOrderCreate, SalesOrderRead, SalesOrderUpdate
from app.services.document_numbering import next_monthly_number
from app.services.exposure_engine import (
    close_open_exposures_for_source,
    reconcile_sales_order_exposures,
)
from app.services.exposure_timeline import (
    emit_exposure_closed,
    emit_exposure_created,
    emit_exposure_recalculated,
)
from app.services.timeline_emitters import correlation_id_from_request_id

router = APIRouter(prefix="/sales-orders", tags=["sales_orders"])


def _generate_so_number() -> str:
    # Backward compatible helper retained for reference.
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:6].upper()
    return f"SO-{ts}-{suffix}"


@router.get("", response_model=List[SalesOrderRead])
def list_sales_orders(
    deal_id: Optional[int] = Query(None),
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
    q = db.query(models.SalesOrder).options(joinedload(models.SalesOrder.customer))
    if deal_id is not None:
        q = q.filter(models.SalesOrder.deal_id == int(deal_id))
    return q.order_by(models.SalesOrder.created_at.desc()).all()


@router.post("", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    payload: SalesOrderCreate,
    request: Request,
    create_deal_if_missing: bool = Query(
        False,
        description=(
            "Legacy escape hatch: when true and deal_id is omitted, "
            "the API will create a new deal automatically."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    customer = db.get(models.Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer not found")
    if payload.unit_price is not None and payload.unit_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Preço unitário deve ser positivo."
        )

    so_number = payload.so_number
    if not so_number:
        so_number = next_monthly_number(db, doc_type="SO", prefix="SO").formatted

    requested_deal_id = getattr(payload, "deal_id", None)
    if requested_deal_id is not None:
        deal = db.get(models.Deal, int(requested_deal_id))
        if not deal:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal not found")
        deal_id = int(deal.id)
        allocation_type = models.DealAllocationType.manual
    else:
        if not create_deal_if_missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="deal_id is required. Create/select a Deal before creating a Sales Order.",
            )

        # Legacy mode: if caller didn't pick one, create a fresh deal and link automatically.
        deal = models.Deal(
            commodity=payload.product,
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
        )
        db.add(deal)
        db.flush()
        deal_id = int(deal.id)
        allocation_type = models.DealAllocationType.auto

    so = models.SalesOrder(
        so_number=so_number,
        deal_id=deal_id,
        customer_id=payload.customer_id,
        product=payload.product,
        total_quantity_mt=payload.total_quantity_mt,
        unit=payload.unit,
        unit_price=payload.unit_price,
        pricing_type=payload.pricing_type,
        pricing_period=payload.pricing_period,
        lme_premium=payload.lme_premium,
        premium=payload.premium,
        reference_price=payload.reference_price,
        fixing_deadline=payload.fixing_deadline,
        expected_delivery_date=payload.expected_delivery_date,
        location=payload.location,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(so)
    db.flush()

    # Keep DealLink consistent (even at creation time).
    db.query(models.DealLink).filter(
        models.DealLink.entity_type == models.DealEntityType.so,
        models.DealLink.entity_id == so.id,
    ).delete(synchronize_session=False)
    db.add(
        models.DealLink(
            deal_id=deal_id,
            entity_type=models.DealEntityType.so,
            entity_id=so.id,
            direction=models.DealDirection.sell,
            quantity_mt=so.total_quantity_mt,
            allocation_type=allocation_type,
        )
    )

    reconcile = reconcile_sales_order_exposures(db=db, so=so)

    db.commit()
    db.refresh(so)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    actor_user_id = getattr(current_user, "id", None)
    for exp_id in reconcile.created_exposure_ids:
        exp = db.get(models.Exposure, exp_id)
        if exp is not None:
            emit_exposure_created(
                db=db,
                exposure=exp,
                correlation_id=correlation_id,
                actor_user_id=actor_user_id,
            )

    return so


@router.get("/{so_id}", response_model=SalesOrderRead)
def get_sales_order(
    so_id: int,
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
    so = (
        db.query(models.SalesOrder)
        .options(joinedload(models.SalesOrder.customer))
        .filter(models.SalesOrder.id == so_id)
        .first()
    )
    if not so:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales Order not found")
    return so


@router.put("/{so_id}", response_model=SalesOrderRead)
def update_sales_order(
    so_id: int,
    payload: SalesOrderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales Order not found")

    data = payload.dict(exclude_unset=True)

    deal_id_specified = "deal_id" in data
    new_deal_id = data.pop("deal_id", None)
    if deal_id_specified and new_deal_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="deal_id cannot be null for sales orders",
        )
    if new_deal_id is not None:
        deal = db.get(models.Deal, int(new_deal_id))
        if not deal:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal not found")
        so.deal_id = int(new_deal_id)
        db.query(models.DealLink).filter(
            models.DealLink.entity_type == models.DealEntityType.so,
            models.DealLink.entity_id == so.id,
        ).delete(synchronize_session=False)
        db.add(
            models.DealLink(
                deal_id=int(deal.id),
                entity_type=models.DealEntityType.so,
                entity_id=so.id,
                direction=models.DealDirection.sell,
                quantity_mt=(data.get("total_quantity_mt") or so.total_quantity_mt),
                allocation_type=models.DealAllocationType.manual,
            )
        )

    for field, value in data.items():
        setattr(so, field, value)

    reconcile = reconcile_sales_order_exposures(db=db, so=so)

    db.add(so)
    db.commit()
    db.refresh(so)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    actor_user_id = getattr(current_user, "id", None)

    for exp_id in reconcile.created_exposure_ids:
        exp = db.get(models.Exposure, exp_id)
        if exp is not None:
            emit_exposure_created(
                db=db,
                exposure=exp,
                correlation_id=correlation_id,
                actor_user_id=actor_user_id,
            )
    for exp_id in reconcile.recalculated_exposure_ids:
        exp = db.get(models.Exposure, exp_id)
        if exp is not None:
            emit_exposure_recalculated(
                db=db,
                exposure=exp,
                correlation_id=correlation_id,
                actor_user_id=actor_user_id,
                reason="sales_order_reconcile",
            )
    for exp_id in reconcile.closed_exposure_ids:
        exp = db.get(models.Exposure, exp_id)
        if exp is not None:
            emit_exposure_closed(
                db=db,
                exposure=exp,
                correlation_id=correlation_id,
                actor_user_id=actor_user_id,
                reason="sales_order_reconcile",
            )

    return so


@router.post("/{so_id}/assign-deal", response_model=SalesOrderRead)
def assign_sales_order_to_deal(
    so_id: int,
    payload: AssignDealRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales Order not found")

    deal = db.get(models.Deal, int(payload.deal_id))
    if not deal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal not found")

    so.deal_id = int(deal.id)

    db.query(models.DealLink).filter(
        models.DealLink.entity_type == models.DealEntityType.so,
        models.DealLink.entity_id == so.id,
    ).delete(synchronize_session=False)
    db.add(
        models.DealLink(
            deal_id=int(deal.id),
            entity_type=models.DealEntityType.so,
            entity_id=so.id,
            direction=models.DealDirection.sell,
            quantity_mt=so.total_quantity_mt,
            allocation_type=models.DealAllocationType.manual,
        )
    )

    db.add(so)
    db.commit()
    db.refresh(so)
    return so


@router.delete("/{so_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_order(
    so_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales Order not found")

    closed_ids = close_open_exposures_for_source(
        db=db,
        source_type=models.MarketObjectType.so,
        source_id=int(so.id),
    )

    db.delete(so)
    db.commit()

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    actor_user_id = getattr(current_user, "id", None)
    for exp_id in closed_ids:
        exp = db.get(models.Exposure, int(exp_id))
        if exp is not None:
            emit_exposure_closed(
                db=db,
                exposure=exp,
                correlation_id=correlation_id,
                actor_user_id=actor_user_id,
                reason="sales_order_deleted",
            )
