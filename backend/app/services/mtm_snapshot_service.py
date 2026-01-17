from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from app import models
from app.schemas.mtm_snapshot import MTMSnapshotCreate
from app.services.exposure_aggregation import compute_net_exposure


def _compute_for_exposure(
    db: Session,
    exposure_id: int,
    price: float,
) -> tuple[float, float, str | None, str | None]:
    exp = db.get(models.Exposure, exposure_id)
    if not exp:
        raise ValueError("Exposure not found")
    qty = exp.quantity_mt
    mtm_val = qty * price
    period = None
    if exp.delivery_date:
        period = exp.delivery_date.strftime("%Y-%m")
    elif exp.sale_date:
        period = exp.sale_date.strftime("%Y-%m")
    elif exp.payment_date:
        period = exp.payment_date.strftime("%Y-%m")
    return qty, mtm_val, exp.product, period


def _compute_for_hedge(
    db: Session,
    hedge_id: int,
    price: float,
) -> tuple[float, float, str | None, str | None]:
    hedge = db.get(models.Hedge, hedge_id)
    if not hedge:
        raise ValueError("Hedge not found")
    qty = hedge.quantity_mt
    mtm_val = (price - hedge.contract_price) * qty
    return qty, mtm_val, hedge.instrument, hedge.period


def _compute_for_net(
    db: Session,
    product: Optional[str],
    period: Optional[str],
    price: float,
) -> tuple[float, float, str | None]:
    rows = compute_net_exposure(db, product=product, period=period)
    if not rows:
        raise ValueError("Net exposure not found")
    qty = sum(r.net for r in rows if r.product == product or product is None)
    mtm_val = qty * price
    return qty, mtm_val, product


def create_snapshot(db: Session, payload: MTMSnapshotCreate) -> models.MTMSnapshot:
    as_of = payload.as_of_date or date.today()
    if (
        payload.object_type in {models.MarketObjectType.exposure, models.MarketObjectType.hedge}
        and payload.object_id is None
    ):
        raise ValueError("object_id is required for exposure and hedge MTM snapshots")

    if payload.object_type == models.MarketObjectType.exposure:
        qty, mtm_val, prod, derived_period = _compute_for_exposure(
            db, payload.object_id or 0, payload.price
        )
        period = payload.period or derived_period
    elif payload.object_type == models.MarketObjectType.hedge:
        qty, mtm_val, prod, hedge_period = _compute_for_hedge(
            db, payload.object_id or 0, payload.price
        )
        period = payload.period or hedge_period
    elif payload.object_type == models.MarketObjectType.net:
        qty, mtm_val, prod = _compute_for_net(db, payload.product, payload.period, payload.price)
        period = payload.period
    else:
        raise ValueError("Unsupported object type")

    snap = models.MTMSnapshot(
        object_type=payload.object_type,
        object_id=payload.object_id,
        product=payload.product or prod,
        period=period,
        price=payload.price,
        quantity_mt=qty,
        mtm_value=mtm_val,
        as_of_date=as_of,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def list_snapshots(
    db: Session,
    object_type: Optional[models.MarketObjectType],
    object_id: Optional[int],
    product: Optional[str],
    period: Optional[str],
    latest: bool = False,
) -> List[models.MTMSnapshot]:
    q = db.query(models.MTMSnapshot)
    if object_type:
        q = q.filter(models.MTMSnapshot.object_type == object_type)
    if object_id is not None:
        q = q.filter(models.MTMSnapshot.object_id == object_id)
    if product:
        q = q.filter(models.MTMSnapshot.product == product)
    if period:
        q = q.filter(models.MTMSnapshot.period == period)
    # Deterministic ordering: created_at can collide (DB precision / fast inserts),
    # so use id as a stable tie-breaker.
    q = q.order_by(models.MTMSnapshot.created_at.desc(), models.MTMSnapshot.id.desc())
    if latest:
        snap = q.first()
        return [snap] if snap else []
    return q.all()
