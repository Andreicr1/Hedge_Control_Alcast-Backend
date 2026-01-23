# ruff: noqa: B008, E501, B904

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import PurchaseOrderCreate, PurchaseOrderRead, PurchaseOrderUpdate
from app.services.document_numbering import next_monthly_number
from app.services.exposure_engine import (
    close_open_exposures_for_source,
    reconcile_purchase_order_exposures,
)
from app.services.exposure_timeline import (
    emit_exposure_closed,
    emit_exposure_created,
    emit_exposure_recalculated,
)
from app.services.timeline_emitters import correlation_id_from_request_id

router = APIRouter(prefix="/purchase-orders", tags=["purchase_orders"])


def _generate_po_number() -> str:
    # Backward compatible helper (used only when caller does not supply a number).
    # Format: PO_001-03.25 (monthly sequence, UTC).
    # NOTE: needs db session in caller; keep this function for historical imports.
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PO-{ts}"


@router.get("", response_model=List[PurchaseOrderRead])
def list_purchase_orders(
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
    q = db.query(models.PurchaseOrder).options(joinedload(models.PurchaseOrder.supplier))
    if deal_id is not None:
        q = q.filter(models.PurchaseOrder.deal_id == int(deal_id))
    return q.order_by(models.PurchaseOrder.created_at.desc()).all()


@router.post("", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    payload: PurchaseOrderCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    supplier = db.get(models.Supplier, payload.supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier not found")

    requested_deal_id = getattr(payload, "deal_id", None)
    if requested_deal_id is not None:
        deal = db.get(models.Deal, int(requested_deal_id))
        if not deal:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal not found")
        deal_id = int(deal.id)
        allocation_type = models.DealAllocationType.manual
    else:
        # Purchase Orders must always be linked to a deal.
        # If caller didn't pick one, we create a fresh deal and link automatically.
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
    if payload.unit_price is not None and payload.unit_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Preço unitário deve ser positivo."
        )

    po_number = payload.po_number
    if not po_number:
        po_number = next_monthly_number(db, doc_type="PO", prefix="PO").formatted

    po = models.PurchaseOrder(
        po_number=po_number,
        deal_id=deal_id,
        supplier_id=payload.supplier_id,
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
        avg_cost=payload.avg_cost,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(po)
    db.flush()

    # Keep DealLink consistent (even at creation time).
    db.query(models.DealLink).filter(
        models.DealLink.entity_type == models.DealEntityType.po,
        models.DealLink.entity_id == po.id,
    ).delete(synchronize_session=False)
    db.add(
        models.DealLink(
            deal_id=deal_id,
            entity_type=models.DealEntityType.po,
            entity_id=po.id,
            direction=models.DealDirection.buy,
            quantity_mt=po.total_quantity_mt,
            allocation_type=allocation_type,
        )
    )

    reconcile = reconcile_purchase_order_exposures(db=db, po=po)

    db.commit()
    db.refresh(po)

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

    return po


@router.get("/{po_id}", response_model=PurchaseOrderRead)
def get_purchase_order(
    po_id: int,
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
    po = (
        db.query(models.PurchaseOrder)
        .options(joinedload(models.PurchaseOrder.supplier))
        .filter(models.PurchaseOrder.id == po_id)
        .first()
    )
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found"
        )
    return po


@router.put("/{po_id}", response_model=PurchaseOrderRead)
def update_purchase_order(
    po_id: int,
    payload: PurchaseOrderUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    po = db.get(models.PurchaseOrder, po_id)
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found"
        )

    data = payload.dict(exclude_unset=True)

    deal_id_specified = "deal_id" in data
    new_deal_id = data.pop("deal_id", None)
    if deal_id_specified and new_deal_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="deal_id cannot be null for purchase orders",
        )
    if new_deal_id is not None:
        if not db.get(models.Deal, int(new_deal_id)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal not found")
        po.deal_id = int(new_deal_id)
        # Keep DealLink consistent: remove any existing PO links then re-link.
        db.query(models.DealLink).filter(
            models.DealLink.entity_type == models.DealEntityType.po,
            models.DealLink.entity_id == po.id,
        ).delete(synchronize_session=False)
        db.add(
            models.DealLink(
                deal_id=int(new_deal_id),
                entity_type=models.DealEntityType.po,
                entity_id=po.id,
                direction=models.DealDirection.buy,
                quantity_mt=po.total_quantity_mt,
                allocation_type=models.DealAllocationType.manual,
            )
        )

    for field, value in data.items():
        setattr(po, field, value)

    reconcile = reconcile_purchase_order_exposures(db=db, po=po)

    db.add(po)
    db.commit()
    db.refresh(po)

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
                reason="purchase_order_reconcile",
            )
    for exp_id in reconcile.closed_exposure_ids:
        exp = db.get(models.Exposure, exp_id)
        if exp is not None:
            emit_exposure_closed(
                db=db,
                exposure=exp,
                correlation_id=correlation_id,
                actor_user_id=actor_user_id,
                reason="purchase_order_reconcile",
            )

    return po


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(
    po_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.comercial)
    ),
):
    po = db.get(models.PurchaseOrder, po_id)
    if not po:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Purchase Order not found"
        )

    closed_ids = close_open_exposures_for_source(
        db=db,
        source_type=models.MarketObjectType.po,
        source_id=int(po.id),
    )

    db.delete(po)
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
                reason="purchase_order_deleted",
            )
