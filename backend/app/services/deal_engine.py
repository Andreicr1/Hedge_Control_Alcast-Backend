from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app import models


def ensure_deal_for_sales_order(db: Session, so: models.SalesOrder) -> models.Deal:
    currency = getattr(so, "currency", None) or "USD"
    deal = models.Deal(commodity=so.product, currency=currency, status=models.DealStatus.open)
    db.add(deal)
    db.flush()

    link = models.DealLink(
        deal_id=deal.id,
        entity_type=models.DealEntityType.so,
        entity_id=so.id,
        direction=models.DealDirection.sell,
        quantity_mt=so.total_quantity_mt,
        allocation_type=models.DealAllocationType.auto,
    )
    db.add(link)
    return deal


def link_purchase_order_to_deal(
    db: Session, po: models.PurchaseOrder, deal_id: Optional[int]
) -> models.Deal:
    if not deal_id:
        raise ValueError("Purchase Order must be explicitly linked to a deal_id")

    deal = db.get(models.Deal, deal_id)
    if not deal:
        raise ValueError(f"Deal {deal_id} not found")

    existing_link = (
        db.query(models.DealLink)
        .filter(
            models.DealLink.entity_type == models.DealEntityType.po,
            models.DealLink.entity_id == po.id,
            models.DealLink.deal_id == deal.id,
        )
        .first()
    )
    if existing_link:
        return deal

    link = models.DealLink(
        deal_id=deal.id,
        entity_type=models.DealEntityType.po,
        entity_id=po.id,
        direction=models.DealDirection.buy,
        quantity_mt=po.total_quantity_mt,
        allocation_type=models.DealAllocationType.manual,
    )
    db.add(link)
    return deal


def link_hedge_to_deal(db: Session, hedge: models.Hedge, deal_id: Optional[int]) -> models.Deal:
    if not deal_id:
        raise ValueError("Hedge must be linked to a deal_id")

    deal = db.get(models.Deal, deal_id)
    if not deal:
        raise ValueError(f"Deal {deal_id} not found")

    existing_link = (
        db.query(models.DealLink)
        .filter(
            models.DealLink.entity_type == models.DealEntityType.hedge,
            models.DealLink.entity_id == hedge.id,
            models.DealLink.deal_id == deal.id,
        )
        .first()
    )
    if existing_link:
        return deal

    direction = (
        models.DealDirection.buy if getattr(hedge, "is_buy", True) else models.DealDirection.sell
    )
    link = models.DealLink(
        deal_id=deal.id,
        entity_type=models.DealEntityType.hedge,
        entity_id=hedge.id,
        direction=direction,
        quantity_mt=hedge.quantity_mt,
        allocation_type=models.DealAllocationType.manual,
    )
    db.add(link)
    return deal


def calculate_deal_pnl(db: Session, deal_id: int, persist_snapshot: bool = True) -> Optional[Dict]:
    deal = db.get(models.Deal, deal_id)
    if not deal:
        return None

    links: List[models.DealLink] = (
        db.query(models.DealLink).filter(models.DealLink.deal_id == deal_id).all()
    )
    so_ids = [link.entity_id for link in links if link.entity_type == models.DealEntityType.so]
    po_ids = [link.entity_id for link in links if link.entity_type == models.DealEntityType.po]
    hedge_ids = [
        link.entity_id for link in links if link.entity_type == models.DealEntityType.hedge
    ]

    physical_revenue = 0.0
    physical_cost = 0.0
    hedge_pnl_realized = 0.0
    hedge_pnl_mtm = 0.0

    physical_legs = []
    hedge_legs = []

    if so_ids:
        for so in db.query(models.SalesOrder).filter(models.SalesOrder.id.in_(so_ids)).all():
            if so.total_quantity_mt is None:
                raise ValueError(f"SO {so.id} has no quantity_mt defined")
            if so.unit_price is None:
                raise ValueError(f"SO {so.id} has no price fixed yet")
            qty = so.total_quantity_mt
            price = so.unit_price
            physical_revenue += price * qty
            physical_legs.append(
                {
                    "source": "SO",
                    "source_id": so.id,
                    "direction": "SELL",
                    "quantity_mt": qty,
                    "pricing_type": so.pricing_type.value,
                    "pricing_reference": so.pricing_period
                    or (so.fixing_deadline.isoformat() if so.fixing_deadline else None),
                    "fixed_price": so.unit_price,
                    "status": so.status.value,
                }
            )

    if po_ids:
        for po in db.query(models.PurchaseOrder).filter(models.PurchaseOrder.id.in_(po_ids)).all():
            if po.total_quantity_mt is None:
                raise ValueError(f"PO {po.id} has no quantity_mt defined")
            if po.unit_price is None:
                raise ValueError(f"PO {po.id} has no price fixed yet")
            qty = po.total_quantity_mt
            price = po.unit_price
            physical_cost += price * qty
            physical_legs.append(
                {
                    "source": "PO",
                    "source_id": po.id,
                    "direction": "BUY",
                    "quantity_mt": qty,
                    "pricing_type": po.pricing_type.value,
                    "pricing_reference": po.pricing_period
                    or (po.fixing_deadline.isoformat() if po.fixing_deadline else None),
                    "fixed_price": po.unit_price,
                    "status": po.status.value,
                }
            )

    if hedge_ids:
        for hedge in db.query(models.Hedge).filter(models.Hedge.id.in_(hedge_ids)).all():
            if hedge.quantity_mt is None:
                raise ValueError(f"Hedge {hedge.id} has no quantity_mt defined")
            if hedge.contract_price is None:
                raise ValueError(f"Hedge {hedge.id} has no contract_price defined")
            entry_price = hedge.contract_price
            qty = hedge.quantity_mt
            direction_label = "BUY" if getattr(hedge, "is_buy", True) else "SELL"

            if hedge.mtm_value is not None:
                mtm_value = hedge.mtm_value
                mtm_price = (
                    hedge.current_market_price
                    if hedge.current_market_price is not None
                    else entry_price
                )
            else:
                if hedge.current_market_price is None:
                    raise ValueError(f"Hedge {hedge.id} has no mtm_price available")
                mtm_price = hedge.current_market_price
                mtm_value = (mtm_price - entry_price) * qty

            if hedge.status == models.HedgeStatus.closed:
                hedge_pnl_realized += mtm_value
                mtm_component = 0.0
            else:
                hedge_pnl_mtm += mtm_value
                mtm_component = mtm_value

            hedge_legs.append(
                {
                    "hedge_id": hedge.id,
                    "direction": direction_label,
                    "quantity_mt": qty,
                    "contract_period": hedge.period,
                    "entry_price": entry_price,
                    "mtm_price": mtm_price,
                    "mtm_value": mtm_component,
                    "status": hedge.status.value,
                }
            )

    net_pnl = physical_revenue + hedge_pnl_realized + hedge_pnl_mtm - physical_cost

    snapshot_ts = datetime.utcnow()
    if persist_snapshot:
        snapshot = models.DealPNLSnapshot(
            deal_id=deal_id,
            timestamp=snapshot_ts,
            physical_revenue=physical_revenue,
            physical_cost=physical_cost,
            hedge_pnl_realized=hedge_pnl_realized,
            hedge_pnl_mtm=hedge_pnl_mtm,
            net_pnl=net_pnl,
        )
        db.add(snapshot)
        db.flush()
        snapshot_ts = snapshot.timestamp

    return {
        "deal_id": deal_id,
        "status": deal.status.value,
        "commodity": deal.commodity,
        "currency": deal.currency,
        "physical_revenue": physical_revenue,
        "physical_cost": physical_cost,
        "hedge_pnl_realized": hedge_pnl_realized,
        "hedge_pnl_mtm": hedge_pnl_mtm,
        "net_pnl": net_pnl,
        "physical_legs": physical_legs,
        "hedge_legs": hedge_legs,
        "snapshot_at": snapshot_ts,
    }
