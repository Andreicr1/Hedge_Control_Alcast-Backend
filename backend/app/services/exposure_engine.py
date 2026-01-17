from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import models
from app.models.domain import ExposureStatus, PricingType


def is_floating_pricing_type(pricing_type: PricingType) -> bool:
    return pricing_type != PricingType.fixed


@dataclass(frozen=True)
class ExposureReconcileResult:
    created_exposure_ids: tuple[int, ...] = ()
    recalculated_exposure_ids: tuple[int, ...] = ()
    closed_exposure_ids: tuple[int, ...] = ()


def close_open_exposures_for_source(
    *,
    db: Session,
    source_type: models.MarketObjectType,
    source_id: int,
) -> tuple[int, ...]:
    open_exposures = _open_exposures_for_source(
        db=db,
        source_type=source_type,
        source_id=int(source_id),
    )
    closed: list[int] = []
    for exp in open_exposures:
        _close_exposure(db=db, exposure=exp)
        closed.append(int(exp.id))
    return tuple(closed)


def _open_exposures_for_source(
    *,
    db: Session,
    source_type: models.MarketObjectType,
    source_id: int,
) -> list[models.Exposure]:
    return (
        db.query(models.Exposure)
        .filter(models.Exposure.source_type == source_type)
        .filter(models.Exposure.source_id == int(source_id))
        .filter(models.Exposure.status != ExposureStatus.closed)
        .order_by(models.Exposure.id.desc())
        .all()
    )


def _hedged_quantity_mt(*, db: Session, exposure_id: int) -> float:
    rows = (
        db.query(models.HedgeExposure)
        .filter(models.HedgeExposure.exposure_id == int(exposure_id))
        .all()
    )
    return float(sum((r.quantity_mt or 0.0) for r in rows))


def _recompute_exposure_status(*, quantity_mt: float, hedged_mt: float) -> ExposureStatus:
    if quantity_mt <= 0:
        return ExposureStatus.closed
    if hedged_mt <= 0:
        return ExposureStatus.open
    if hedged_mt + 1e-9 < quantity_mt:
        return ExposureStatus.partially_hedged
    return ExposureStatus.hedged


def _close_exposure(*, db: Session, exposure: models.Exposure) -> None:
    exposure.status = ExposureStatus.closed
    db.add(exposure)

    # Cancel any pending tasks tied to this exposure.
    tasks = db.query(models.HedgeTask).filter(models.HedgeTask.exposure_id == exposure.id).all()
    for t in tasks:
        if t.status not in {models.HedgeTaskStatus.completed, models.HedgeTaskStatus.cancelled}:
            t.status = models.HedgeTaskStatus.cancelled
            db.add(t)


def reconcile_sales_order_exposures(
    *,
    db: Session,
    so: models.SalesOrder,
) -> ExposureReconcileResult:
    floating = is_floating_pricing_type(so.pricing_type)
    is_open = getattr(so, "status", None) not in {
        models.OrderStatus.cancelled,
        models.OrderStatus.completed,
    }
    open_exposures = _open_exposures_for_source(
        db=db,
        source_type=models.MarketObjectType.so,
        source_id=int(so.id),
    )

    created: list[int] = []
    recalculated: list[int] = []
    closed: list[int] = []

    # Guardrail: prevent multiple concurrent open exposures for the same source.
    # Keep the most recent (highest id) and close the rest.
    if len(open_exposures) > 1:
        for older in open_exposures[1:]:
            _close_exposure(db=db, exposure=older)
            closed.append(int(older.id))
        open_exposures = open_exposures[:1]

    if (not floating) or (not is_open):
        for exp in open_exposures:
            _close_exposure(db=db, exposure=exp)
            closed.append(int(exp.id))
        return ExposureReconcileResult(
            created_exposure_ids=tuple(created),
            recalculated_exposure_ids=tuple(recalculated),
            closed_exposure_ids=tuple(closed),
        )

    if not open_exposures:
        exp = models.Exposure(
            source_type=models.MarketObjectType.so,
            source_id=int(so.id),
            exposure_type=models.ExposureType.active,
            quantity_mt=float(so.total_quantity_mt),
            product=so.product,
            payment_date=None,
            delivery_date=so.expected_delivery_date,
            sale_date=None,
            status=ExposureStatus.open,
        )
        db.add(exp)
        db.flush()
        task = models.HedgeTask(exposure_id=exp.id)
        db.add(task)
        created.append(int(exp.id))
        return ExposureReconcileResult(
            created_exposure_ids=tuple(created),
            recalculated_exposure_ids=tuple(recalculated),
            closed_exposure_ids=tuple(closed),
        )

    # Recalculate latest exposure in-place.
    exp = open_exposures[0]
    changed = False

    new_qty = float(so.total_quantity_mt)
    if abs(float(exp.quantity_mt) - new_qty) > 1e-9:
        exp.quantity_mt = new_qty
        changed = True

    if exp.product != so.product:
        exp.product = so.product
        changed = True

    if exp.delivery_date != so.expected_delivery_date:
        exp.delivery_date = so.expected_delivery_date
        changed = True

    hedged_mt = _hedged_quantity_mt(db=db, exposure_id=int(exp.id))
    new_status = _recompute_exposure_status(quantity_mt=new_qty, hedged_mt=hedged_mt)
    if exp.status != new_status:
        if new_status == ExposureStatus.closed:
            _close_exposure(db=db, exposure=exp)
            closed.append(int(exp.id))
            changed = True
        else:
            exp.status = new_status
            changed = True

    if changed and int(exp.id) not in set(closed):
        db.add(exp)
        recalculated.append(int(exp.id))

    return ExposureReconcileResult(
        created_exposure_ids=tuple(created),
        recalculated_exposure_ids=tuple(recalculated),
        closed_exposure_ids=tuple(closed),
    )


def reconcile_purchase_order_exposures(
    *,
    db: Session,
    po: models.PurchaseOrder,
) -> ExposureReconcileResult:
    floating = is_floating_pricing_type(po.pricing_type)
    is_open = getattr(po, "status", None) not in {
        models.OrderStatus.cancelled,
        models.OrderStatus.completed,
    }
    open_exposures = _open_exposures_for_source(
        db=db,
        source_type=models.MarketObjectType.po,
        source_id=int(po.id),
    )

    created: list[int] = []
    recalculated: list[int] = []
    closed: list[int] = []

    # Guardrail: prevent multiple concurrent open exposures for the same source.
    if len(open_exposures) > 1:
        for older in open_exposures[1:]:
            _close_exposure(db=db, exposure=older)
            closed.append(int(older.id))
        open_exposures = open_exposures[:1]

    if (not floating) or (not is_open):
        for exp in open_exposures:
            _close_exposure(db=db, exposure=exp)
            closed.append(int(exp.id))
        return ExposureReconcileResult(
            created_exposure_ids=tuple(created),
            recalculated_exposure_ids=tuple(recalculated),
            closed_exposure_ids=tuple(closed),
        )

    if not open_exposures:
        exp = models.Exposure(
            source_type=models.MarketObjectType.po,
            source_id=int(po.id),
            exposure_type=models.ExposureType.passive,
            quantity_mt=float(po.total_quantity_mt),
            product=po.product,
            payment_date=None,
            delivery_date=po.expected_delivery_date,
            sale_date=None,
            status=ExposureStatus.open,
        )
        db.add(exp)
        db.flush()
        task = models.HedgeTask(exposure_id=exp.id)
        db.add(task)
        created.append(int(exp.id))
        return ExposureReconcileResult(
            created_exposure_ids=tuple(created),
            recalculated_exposure_ids=tuple(recalculated),
            closed_exposure_ids=tuple(closed),
        )

    exp = open_exposures[0]
    changed = False

    new_qty = float(po.total_quantity_mt)
    if abs(float(exp.quantity_mt) - new_qty) > 1e-9:
        exp.quantity_mt = new_qty
        changed = True

    if exp.product != po.product:
        exp.product = po.product
        changed = True

    if exp.delivery_date != po.expected_delivery_date:
        exp.delivery_date = po.expected_delivery_date
        changed = True

    hedged_mt = _hedged_quantity_mt(db=db, exposure_id=int(exp.id))
    new_status = _recompute_exposure_status(quantity_mt=new_qty, hedged_mt=hedged_mt)
    if exp.status != new_status:
        if new_status == ExposureStatus.closed:
            _close_exposure(db=db, exposure=exp)
            closed.append(int(exp.id))
            changed = True
        else:
            exp.status = new_status
            changed = True

    if changed and int(exp.id) not in set(closed):
        db.add(exp)
        recalculated.append(int(exp.id))

    return ExposureReconcileResult(
        created_exposure_ids=tuple(created),
        recalculated_exposure_ids=tuple(recalculated),
        closed_exposure_ids=tuple(closed),
    )
