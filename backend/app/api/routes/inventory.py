import csv
import io
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import InventoryItem

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get(
    "",
    response_model=List[InventoryItem],
    dependencies=[
        Depends(
            require_roles(
                models.RoleName.admin,
                models.RoleName.comercial,
                models.RoleName.financeiro,
                models.RoleName.estoque,
            )
        )
    ],
)
def list_inventory(
    db: Session = Depends(get_db),
    product: Optional[str] = Query(None, description="Filter by aluminum_type"),
    min_available_tons: Optional[float] = Query(None, description="Minimum available tons"),
    location: Optional[str] = Query(None, description="Filter by warehouse location name"),
    arrival_start: Optional[date] = Query(None, description="Filter by arrival/start date"),
    arrival_end: Optional[date] = Query(None, description="Filter by arrival/end date"),
    export: Optional[str] = Query(None, description="Set to csv to export"),
):
    query = db.query(models.PurchaseOrder).outerjoin(models.WarehouseLocation)

    if product:
        query = query.filter(models.PurchaseOrder.aluminum_type == product)
    if location:
        query = query.filter(models.WarehouseLocation.name == location)
    if arrival_start:
        query = query.filter(models.PurchaseOrder.arrival_date >= arrival_start)
    if arrival_end:
        query = query.filter(models.PurchaseOrder.arrival_date <= arrival_end)

    # exclude fully settled POs
    query = query.filter(models.PurchaseOrder.status != models.OrderStatus.completed)

    pos = query.all()

    # pre-compute committed tons/count by PO
    committed_data = {
        row.purchase_order_id: (row.committed_tons or 0.0, row.links_count or 0)
        for row in (
            db.query(
                models.SoPoLink.purchase_order_id.label("purchase_order_id"),
                func.sum(
                    func.coalesce(models.SalesOrder.quantity_tons, 0)
                    * func.coalesce(models.SoPoLink.link_ratio, 1.0)
                ).label("committed_tons"),
                func.count(models.SoPoLink.id).label("links_count"),
            )
            .join(models.SalesOrder, models.SoPoLink.sales_order_id == models.SalesOrder.id)
            .group_by(models.SoPoLink.purchase_order_id)
            .all()
        )
    }

    # latest MTM per PO
    mtm_latest = (
        db.query(
            models.MtmRecord.object_id.label("po_id"),
            func.max(models.MtmRecord.as_of_date).label("max_date"),
        )
        .filter(models.MtmRecord.object_type == models.MarketObjectType.po)
        .group_by(models.MtmRecord.object_id)
        .subquery()
    )
    mtm_map = {
        rec.object_id: rec.mtm_value
        for rec in (
            db.query(models.MtmRecord)
            .join(
                mtm_latest,
                (models.MtmRecord.object_id == mtm_latest.c.po_id)
                & (models.MtmRecord.as_of_date == mtm_latest.c.max_date),
            )
            .all()
        )
    }

    items: List[InventoryItem] = []
    for po in pos:
        committed_tons, committed_links = committed_data.get(po.id, (0.0, 0))
        available = max((po.quantity_tons or 0) - committed_tons, 0)
        if min_available_tons is not None and available < min_available_tons:
            continue

        item = InventoryItem(
            lot_code=po.code,
            product=po.aluminum_type,
            available_tons=available,
            committed_links=int(committed_links),
            committed_tons=committed_tons,
            location=po.location.name if po.location else None,
            avg_cost=po.avg_cost,
            arrival_date=po.arrival_date,
            mtm_value=mtm_map.get(po.id),
            purchase_order_id=po.id,
        )
        items.append(item)

    if export and export.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "lot_code",
                "product",
                "location",
                "available_tons",
                "committed_tons",
                "committed_links",
                "avg_cost",
                "mtm_value",
                "arrival_date",
            ]
        )
        for item in items:
            writer.writerow(
                [
                    item.lot_code,
                    item.product,
                    item.location or "",
                    item.available_tons,
                    item.committed_tons,
                    item.committed_links,
                    item.avg_cost if item.avg_cost is not None else "",
                    item.mtm_value if item.mtm_value is not None else "",
                    item.arrival_date.isoformat() if item.arrival_date else "",
                ]
            )
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=inventory.csv"},
        )

    return items
