from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app import models
from app.schemas.cashflow import CashflowItemRead
from app.services.cashflow_service import build_cashflow_items


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _dt_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _canonicalize_payload_json(payload_json: str | None) -> str | None:
    if payload_json is None:
        return None
    try:
        parsed = json.loads(payload_json)
    except Exception:
        return payload_json
    return _canonical_json(parsed)


def _rows_for_sales_orders(sales_orders: Iterable[models.SalesOrder]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for so in sorted(sales_orders, key=lambda s: s.id):
        payload = {
            "id": so.id,
            "so_number": so.so_number,
            "deal_id": so.deal_id,
            "customer_id": so.customer_id,
            "product": so.product,
            "total_quantity_mt": so.total_quantity_mt,
            "unit_price": so.unit_price,
            "pricing_type": so.pricing_type.value,
            "pricing_period": so.pricing_period,
            "status": so.status.value,
            "created_at": _dt_iso(so.created_at),
        }
        rows.append(
            {
                "record_type": "sales_order",
                "record_id": str(so.id),
                "created_at": _dt_iso(so.created_at) or "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def _rows_for_purchase_orders(
    purchase_orders: Iterable[models.PurchaseOrder],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for po in sorted(purchase_orders, key=lambda p: p.id):
        payload = {
            "id": po.id,
            "po_number": po.po_number,
            "deal_id": po.deal_id,
            "supplier_id": po.supplier_id,
            "product": po.product,
            "total_quantity_mt": po.total_quantity_mt,
            "unit_price": po.unit_price,
            "pricing_type": po.pricing_type.value,
            "pricing_period": po.pricing_period,
            "status": po.status.value,
            "created_at": _dt_iso(po.created_at),
        }
        rows.append(
            {
                "record_type": "purchase_order",
                "record_id": str(po.id),
                "created_at": _dt_iso(po.created_at) or "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def _rows_for_exposures(exposures: Iterable[models.Exposure]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for e in sorted(exposures, key=lambda x: x.id):
        payload = {
            "id": e.id,
            "source_type": e.source_type.value,
            "source_id": e.source_id,
            "exposure_type": e.exposure_type.value,
            "quantity_mt": e.quantity_mt,
            "product": e.product,
            "status": e.status.value,
            "created_at": _dt_iso(e.created_at),
        }
        rows.append(
            {
                "record_type": "exposure",
                "record_id": str(e.id),
                "created_at": _dt_iso(e.created_at) or "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def _rows_for_rfqs(rfqs: Iterable[models.Rfq]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for rfq in sorted(rfqs, key=lambda r: r.id):
        payload = {
            "id": rfq.id,
            "rfq_number": rfq.rfq_number,
            "deal_id": rfq.deal_id,
            "so_id": rfq.so_id,
            "quantity_mt": rfq.quantity_mt,
            "period": rfq.period,
            "status": rfq.status.value,
            "sent_at": _dt_iso(rfq.sent_at),
            "awarded_at": _dt_iso(rfq.awarded_at),
            "created_at": _dt_iso(rfq.created_at),
        }
        rows.append(
            {
                "record_type": "rfq",
                "record_id": str(rfq.id),
                "created_at": _dt_iso(rfq.created_at) or "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def _rows_for_contracts(contracts: Iterable[models.Contract]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for c in sorted(contracts, key=lambda x: x.contract_id):
        payload = {
            "contract_id": c.contract_id,
            "deal_id": c.deal_id,
            "rfq_id": c.rfq_id,
            "counterparty_id": c.counterparty_id,
            "status": c.status,
            "trade_index": c.trade_index,
            "quote_group_id": c.quote_group_id,
            "settlement_date": c.settlement_date.isoformat() if c.settlement_date else None,
            "trade_snapshot": c.trade_snapshot,
            "created_at": _dt_iso(c.created_at),
        }
        rows.append(
            {
                "record_type": "contract",
                "record_id": str(c.contract_id),
                "created_at": _dt_iso(c.created_at) or "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def _rows_for_mtm_snapshots(snapshots: Iterable[models.MTMSnapshot]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for s in sorted(snapshots, key=lambda x: (x.as_of_date, x.id)):
        payload = {
            "id": s.id,
            "object_type": s.object_type.value,
            "object_id": s.object_id,
            "product": s.product,
            "period": s.period,
            "price": s.price,
            "quantity_mt": s.quantity_mt,
            "mtm_value": s.mtm_value,
            "as_of_date": s.as_of_date.isoformat(),
            "created_at": _dt_iso(s.created_at),
        }
        rows.append(
            {
                "record_type": "mtm_snapshot",
                "record_id": str(s.id),
                "created_at": _dt_iso(s.created_at) or "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def _rows_for_cashflow(items: Iterable[CashflowItemRead]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in sorted(items, key=lambda x: x.contract_id):
        payload = item.dict()
        rows.append(
            {
                "record_type": "cashflow_item",
                "record_id": str(item.contract_id),
                "created_at": "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def _rows_for_audit_logs(logs: Iterable[models.AuditLog]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    logs_sorted = sorted(logs, key=lambda a: (a.created_at, a.id))
    for a in logs_sorted:
        payload = {
            "id": a.id,
            "action": a.action,
            "user_id": a.user_id,
            "rfq_id": a.rfq_id,
            "payload_json": _canonicalize_payload_json(a.payload_json),
            "request_id": a.request_id,
            "ip": a.ip,
            "user_agent": a.user_agent,
            "created_at": _dt_iso(a.created_at),
        }
        rows.append(
            {
                "record_type": "audit_log",
                "record_id": str(a.id),
                "created_at": _dt_iso(a.created_at) or "",
                "payload_json": _canonical_json(payload),
            }
        )
    return rows


def build_state_at_time_csv_bytes(
    db: Session,
    *,
    as_of: datetime,
    filters: dict[str, Any] | None,
) -> bytes:
    """Builds a deterministic 'state at time T' CSV export.

    This is a read-only snapshot: it queries existing entities and includes join keys.
    """

    subject_type = (filters or {}).get("subject_type")
    subject_id = (filters or {}).get("subject_id")

    if (subject_type is None) != (subject_id is None):
        raise ValueError("subject_type and subject_id must be provided together")

    sales_orders: list[models.SalesOrder] = []
    purchase_orders: list[models.PurchaseOrder] = []
    rfqs: list[models.Rfq] = []
    contracts: list[models.Contract] = []
    exposures: list[models.Exposure] = []
    mtm_snapshots: list[models.MTMSnapshot] = []
    audit_logs: list[models.AuditLog] = []

    if subject_type is None:
        sales_orders = (
            db.query(models.SalesOrder).filter(models.SalesOrder.created_at <= as_of).all()
        )
        purchase_orders = (
            db.query(models.PurchaseOrder).filter(models.PurchaseOrder.created_at <= as_of).all()
        )
        rfqs = db.query(models.Rfq).filter(models.Rfq.created_at <= as_of).all()
        contracts = db.query(models.Contract).filter(models.Contract.created_at <= as_of).all()
        exposures = db.query(models.Exposure).filter(models.Exposure.created_at <= as_of).all()
        audit_logs = db.query(models.AuditLog).filter(models.AuditLog.created_at <= as_of).all()
    elif subject_type == "rfq":
        rfq = (
            db.query(models.Rfq)
            .filter(models.Rfq.id == int(subject_id))
            .filter(models.Rfq.created_at <= as_of)
            .first()
        )
        if rfq is not None:
            rfqs = [rfq]

        so = (
            db.query(models.SalesOrder)
            .filter(models.SalesOrder.id == int(rfq.so_id))
            .filter(models.SalesOrder.created_at <= as_of)
            .first()
            if rfq is not None
            else None
        )
        if so is not None:
            sales_orders = [so]

        deal_id = None
        if rfq is not None and rfq.deal_id is not None:
            deal_id = int(rfq.deal_id)
        elif so is not None and so.deal_id is not None:
            deal_id = int(so.deal_id)

        if deal_id is not None:
            purchase_orders = (
                db.query(models.PurchaseOrder)
                .filter(models.PurchaseOrder.deal_id == deal_id)
                .filter(models.PurchaseOrder.created_at <= as_of)
                .all()
            )

        rfq_ids = [r.id for r in rfqs]
        if rfq_ids:
            contracts = (
                db.query(models.Contract)
                .filter(models.Contract.rfq_id.in_(rfq_ids))
                .filter(models.Contract.created_at <= as_of)
                .all()
            )

            audit_logs = (
                db.query(models.AuditLog)
                .filter(models.AuditLog.rfq_id.in_(rfq_ids))
                .filter(models.AuditLog.created_at <= as_of)
                .all()
            )

        so_ids = [s.id for s in sales_orders]
        po_ids = [p.id for p in purchase_orders]
        if so_ids or po_ids:
            q = db.query(models.Exposure).filter(models.Exposure.created_at <= as_of)
            if so_ids and po_ids:
                q = q.filter(
                    (
                        (models.Exposure.source_type == models.MarketObjectType.so)
                        & (models.Exposure.source_id.in_(so_ids))
                    )
                    | (
                        (models.Exposure.source_type == models.MarketObjectType.po)
                        & (models.Exposure.source_id.in_(po_ids))
                    )
                )
            elif so_ids:
                q = q.filter(models.Exposure.source_type == models.MarketObjectType.so).filter(
                    models.Exposure.source_id.in_(so_ids)
                )
            else:
                q = q.filter(models.Exposure.source_type == models.MarketObjectType.po).filter(
                    models.Exposure.source_id.in_(po_ids)
                )
            exposures = q.all()

        mtm_q = db.query(models.MTMSnapshot).filter(models.MTMSnapshot.as_of_date <= as_of.date())
        if so_ids and po_ids:
            mtm_q = mtm_q.filter(
                (
                    (models.MTMSnapshot.object_type == models.MarketObjectType.so)
                    & (models.MTMSnapshot.object_id.in_(so_ids))
                )
                | (
                    (models.MTMSnapshot.object_type == models.MarketObjectType.po)
                    & (models.MTMSnapshot.object_id.in_(po_ids))
                )
            )
        elif so_ids:
            mtm_q = mtm_q.filter(
                models.MTMSnapshot.object_type == models.MarketObjectType.so
            ).filter(models.MTMSnapshot.object_id.in_(so_ids))
        elif po_ids:
            mtm_q = mtm_q.filter(
                models.MTMSnapshot.object_type == models.MarketObjectType.po
            ).filter(models.MTMSnapshot.object_id.in_(po_ids))
        else:
            mtm_q = mtm_q.filter(models.MTMSnapshot.id == -1)
        mtm_snapshots = mtm_q.all()
    elif subject_type == "so":
        so = (
            db.query(models.SalesOrder)
            .filter(models.SalesOrder.id == int(subject_id))
            .filter(models.SalesOrder.created_at <= as_of)
            .first()
        )
        if so is not None:
            sales_orders = [so]

        rfqs = (
            db.query(models.Rfq)
            .filter(models.Rfq.so_id == int(subject_id))
            .filter(models.Rfq.created_at <= as_of)
            .all()
        )
        rfq_ids = [r.id for r in rfqs]
        if rfq_ids:
            contracts = (
                db.query(models.Contract)
                .filter(models.Contract.rfq_id.in_(rfq_ids))
                .filter(models.Contract.created_at <= as_of)
                .all()
            )

            audit_logs = (
                db.query(models.AuditLog)
                .filter(models.AuditLog.rfq_id.in_(rfq_ids))
                .filter(models.AuditLog.created_at <= as_of)
                .all()
            )

        if so is not None and so.deal_id is not None:
            purchase_orders = (
                db.query(models.PurchaseOrder)
                .filter(models.PurchaseOrder.deal_id == int(so.deal_id))
                .filter(models.PurchaseOrder.created_at <= as_of)
                .all()
            )

        so_ids = [s.id for s in sales_orders]
        po_ids = [p.id for p in purchase_orders]
        q = db.query(models.Exposure).filter(models.Exposure.created_at <= as_of)
        if so_ids and po_ids:
            q = q.filter(
                (
                    (models.Exposure.source_type == models.MarketObjectType.so)
                    & (models.Exposure.source_id.in_(so_ids))
                )
                | (
                    (models.Exposure.source_type == models.MarketObjectType.po)
                    & (models.Exposure.source_id.in_(po_ids))
                )
            )
        elif so_ids:
            q = q.filter(models.Exposure.source_type == models.MarketObjectType.so).filter(
                models.Exposure.source_id.in_(so_ids)
            )
        elif po_ids:
            q = q.filter(models.Exposure.source_type == models.MarketObjectType.po).filter(
                models.Exposure.source_id.in_(po_ids)
            )
        else:
            q = q.filter(models.Exposure.id == -1)
        exposures = q.all()

        mtm_q = db.query(models.MTMSnapshot).filter(models.MTMSnapshot.as_of_date <= as_of.date())
        if so_ids and po_ids:
            mtm_q = mtm_q.filter(
                (
                    (models.MTMSnapshot.object_type == models.MarketObjectType.so)
                    & (models.MTMSnapshot.object_id.in_(so_ids))
                )
                | (
                    (models.MTMSnapshot.object_type == models.MarketObjectType.po)
                    & (models.MTMSnapshot.object_id.in_(po_ids))
                )
            )
        elif so_ids:
            mtm_q = mtm_q.filter(
                models.MTMSnapshot.object_type == models.MarketObjectType.so
            ).filter(models.MTMSnapshot.object_id.in_(so_ids))
        elif po_ids:
            mtm_q = mtm_q.filter(
                models.MTMSnapshot.object_type == models.MarketObjectType.po
            ).filter(models.MTMSnapshot.object_id.in_(po_ids))
        else:
            mtm_q = mtm_q.filter(models.MTMSnapshot.id == -1)
        mtm_snapshots = mtm_q.all()
    else:
        raise ValueError("unsupported subject_type")

    cashflow_items = build_cashflow_items(db, contracts, as_of=as_of.date())

    rows: list[dict[str, str]] = []
    rows.extend(_rows_for_sales_orders(sales_orders))
    rows.extend(_rows_for_purchase_orders(purchase_orders))
    rows.extend(_rows_for_exposures(exposures))
    rows.extend(_rows_for_rfqs(rfqs))
    rows.extend(_rows_for_contracts(contracts))
    rows.extend(_rows_for_mtm_snapshots(mtm_snapshots))
    rows.extend(_rows_for_cashflow(cashflow_items))
    rows.extend(_rows_for_audit_logs(audit_logs))

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf,
        fieldnames=["record_type", "record_id", "created_at", "payload_json"],
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    return buf.getvalue().encode("utf-8")
