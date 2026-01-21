from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

from app import models


def _is_floating_source(
    exp: models.Exposure,
    *,
    so_by_id: dict[int, models.SalesOrder],
    po_by_id: dict[int, models.PurchaseOrder],
) -> bool:
    if exp.source_type == models.MarketObjectType.so:
        so = so_by_id.get(int(exp.source_id))
        if so is None:
            return False
        return so.pricing_type in {
            models.PriceType.AVG,
            models.PriceType.AVG_INTER,
            models.PriceType.C2R,
        }
    if exp.source_type == models.MarketObjectType.po:
        po = po_by_id.get(int(exp.source_id))
        if po is None:
            return False
        return po.pricing_type in {
            models.PriceType.AVG,
            models.PriceType.AVG_INTER,
            models.PriceType.C2R,
        }
    return True


@dataclass
class NetExposureRow:
    product: str
    period: str
    gross_active: float
    gross_passive: float
    hedged: float
    net: float


def _period_bucket(exposure: models.Exposure) -> str:
    if exposure.delivery_date:
        return exposure.delivery_date.strftime("%Y-%m")
    if exposure.sale_date:
        return exposure.sale_date.strftime("%Y-%m")
    if exposure.payment_date:
        return exposure.payment_date.strftime("%Y-%m")
    return "unknown"


def compute_net_exposure(
    db: Session,
    product: Optional[str] = None,
    period: Optional[str] = None,
) -> List[NetExposureRow]:
    exposures = (
        db.query(models.Exposure)
        .filter(models.Exposure.status != models.ExposureStatus.closed)
        .all()
    )
    links = db.query(models.HedgeExposure).all()

    so_by_id: dict[int, models.SalesOrder] = {}
    po_by_id: dict[int, models.PurchaseOrder] = {}
    if exposures:
        so_ids = [int(e.source_id) for e in exposures if e.source_type == models.MarketObjectType.so]
        po_ids = [int(e.source_id) for e in exposures if e.source_type == models.MarketObjectType.po]
        if so_ids:
            for so in db.query(models.SalesOrder).filter(models.SalesOrder.id.in_(so_ids)).all():
                so_by_id[int(so.id)] = so
        if po_ids:
            for po in db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id.in_(po_ids)).all():
                po_by_id[int(po.id)] = po

    hedged_map = defaultdict(float)
    for link in links:
        hedged_map[(link.exposure_id)] += link.quantity_mt

    buckets = defaultdict(lambda: {"active": 0.0, "passive": 0.0, "hedged": 0.0})

    for exp in exposures:
        if not _is_floating_source(exp, so_by_id=so_by_id, po_by_id=po_by_id):
            continue
        if product and exp.product and exp.product != product:
            continue
        bucket = _period_bucket(exp)
        if period and bucket != period:
            continue
        key = (exp.product or "unknown", bucket)
        buckets[key][exp.exposure_type.value] += exp.quantity_mt
        buckets[key]["hedged"] += hedged_map.get(exp.id, 0.0)

    rows: List[NetExposureRow] = []
    for (prod, buck), vals in buckets.items():
        gross_active = vals.get("active", 0.0)
        gross_passive = vals.get("passive", 0.0)
        hedged = vals.get("hedged", 0.0)
        net = gross_active - gross_passive - hedged
        rows.append(
            NetExposureRow(
                product=prod,
                period=buck,
                gross_active=gross_active,
                gross_passive=gross_passive,
                hedged=hedged,
                net=net,
            )
        )

    rows.sort(key=lambda r: (r.product or "", r.period or ""))
    return rows
