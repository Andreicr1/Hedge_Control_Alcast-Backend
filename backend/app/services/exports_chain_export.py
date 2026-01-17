from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.exports_pdf import build_simple_text_pdf_bytes


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _dt_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _deterministic_zip_bytes(files: Iterable[tuple[str, bytes]]) -> bytes:
    """Build deterministic zip bytes.

    Ensures stable timestamps, ordering, and metadata so the resulting bytes are
    stable for the same file list and file contents.
    """

    buf = io.BytesIO()

    # NOTE: ZipInfo.date_time minimum is 1980-01-01.
    fixed_dt = (1980, 1, 1, 0, 0, 0)

    with zipfile.ZipFile(buf, mode="w") as zf:
        for name, content in files:
            zi = zipfile.ZipInfo(filename=name, date_time=fixed_dt)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3  # Unix
            # Ensure stable permissions (rw-r--r--)
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, content, compress_type=zipfile.ZIP_DEFLATED)

    return buf.getvalue()


def _subject_filter(filters: dict[str, Any] | None) -> tuple[str | None, int | None]:
    subject_type = (filters or {}).get("subject_type")
    subject_id = (filters or {}).get("subject_id")

    if (subject_type is None) != (subject_id is None):
        raise ValueError("subject_type and subject_id must be provided together")

    if subject_type is not None:
        subject_type = str(subject_type).strip().lower()
    if subject_id is not None:
        subject_id = int(subject_id)

    return subject_type, subject_id


def _entity_row(*, entity_type: str, entity_id: str, payload: dict[str, Any]) -> dict[str, str]:
    return {
        "record_type": "entity",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload_json": _canonical_json(payload),
    }


def _relation_row(
    *,
    from_type: str,
    from_id: str,
    relation: str,
    to_type: str,
    to_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    return {
        "record_type": "relation",
        "from_type": from_type,
        "from_id": from_id,
        "relation": relation,
        "to_type": to_type,
        "to_id": to_id,
        "payload_json": _canonical_json(payload or {}),
    }


def build_chain_export_rows(
    db: Session,
    *,
    as_of: datetime,
    filters: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Build a deterministic set of chain rows.

    The export focuses on join keys and relationships across core entities.
    """

    subject_type, subject_id = _subject_filter(filters)

    # Seed sets
    deal_ids: set[int] = set()
    rfq_ids: set[int] = set()
    contract_ids: set[str] = set()
    so_ids: set[int] = set()
    po_ids: set[int] = set()
    exposure_ids: set[int] = set()
    hedge_ids: set[int] = set()

    def _add_deal_id(v: int | None) -> None:
        if v is not None:
            deal_ids.add(int(v))

    if subject_type is None:
        # Whole-of-system snapshot (bounded only by as_of)
        deal_ids.update(
            [d.id for d in db.query(models.Deal).filter(models.Deal.created_at <= as_of).all()]
        )
        rfq_ids.update(
            [r.id for r in db.query(models.Rfq).filter(models.Rfq.created_at <= as_of).all()]
        )
        contract_ids.update(
            [
                c.contract_id
                for c in db.query(models.Contract).filter(models.Contract.created_at <= as_of).all()
            ]
        )
        so_ids.update(
            [
                so.id
                for so in db.query(models.SalesOrder)
                .filter(models.SalesOrder.created_at <= as_of)
                .all()
            ]
        )
        po_ids.update(
            [
                po.id
                for po in db.query(models.PurchaseOrder)
                .filter(models.PurchaseOrder.created_at <= as_of)
                .all()
            ]
        )
        exposure_ids.update(
            [
                e.id
                for e in db.query(models.Exposure).filter(models.Exposure.created_at <= as_of).all()
            ]
        )
        hedge_ids.update(
            [h.id for h in db.query(models.Hedge).filter(models.Hedge.created_at <= as_of).all()]
        )
    else:
        if subject_type in {"deal"}:
            deal_ids.add(subject_id or 0)
        elif subject_type in {"rfq"}:
            rfq_ids.add(subject_id or 0)
        elif subject_type in {"sales_order", "so"}:
            so_ids.add(subject_id or 0)
        elif subject_type in {"purchase_order", "po"}:
            po_ids.add(subject_id or 0)
        elif subject_type in {"exposure"}:
            exposure_ids.add(subject_id or 0)
        elif subject_type in {"hedge"}:
            hedge_ids.add(subject_id or 0)
        else:
            raise ValueError(f"Unsupported subject_type for chain_export: {subject_type}")

        # Expand neighborhood in a deterministic, small-radius way.
        if rfq_ids:
            rfqs = (
                db.query(models.Rfq)
                .filter(models.Rfq.id.in_(sorted(rfq_ids)))
                .filter(models.Rfq.created_at <= as_of)
                .all()
            )
            for r in rfqs:
                _add_deal_id(r.deal_id)
                so_ids.add(int(r.so_id))
                if r.hedge_id is not None:
                    hedge_ids.add(int(r.hedge_id))

        if contract_ids:
            contracts = (
                db.query(models.Contract)
                .filter(models.Contract.contract_id.in_(sorted(contract_ids)))
                .filter(models.Contract.created_at <= as_of)
                .all()
            )
            for c in contracts:
                deal_ids.add(int(c.deal_id))
                rfq_ids.add(int(c.rfq_id))
            exposure_ids.update(
                [
                    ce.exposure_id
                    for ce in db.query(models.ContractExposure)
                    .filter(models.ContractExposure.contract_id.in_(sorted(contract_ids)))
                    .filter(models.ContractExposure.created_at <= as_of)
                    .all()
                ]
            )

        if deal_ids:
            rfq_ids.update(
                [
                    r.id
                    for r in db.query(models.Rfq)
                    .filter(models.Rfq.deal_id.in_(sorted(deal_ids)))
                    .filter(models.Rfq.created_at <= as_of)
                    .all()
                ]
            )
            contract_ids.update(
                [
                    c.contract_id
                    for c in db.query(models.Contract)
                    .filter(models.Contract.deal_id.in_(sorted(deal_ids)))
                    .filter(models.Contract.created_at <= as_of)
                    .all()
                ]
            )

        if so_ids:
            hedge_ids.update(
                [
                    h.id
                    for h in db.query(models.Hedge)
                    .filter(models.Hedge.so_id.in_(sorted(so_ids)))
                    .filter(models.Hedge.created_at <= as_of)
                    .all()
                ]
            )

        if exposure_ids:
            contract_ids.update(
                [
                    ce.contract_id
                    for ce in db.query(models.ContractExposure)
                    .filter(models.ContractExposure.exposure_id.in_(sorted(exposure_ids)))
                    .filter(models.ContractExposure.created_at <= as_of)
                    .all()
                ]
            )
            exposure_ids.update(
                [
                    e.id
                    for e in db.query(models.Exposure)
                    .filter(models.Exposure.source_type == models.MarketObjectType.so)
                    .filter(models.Exposure.source_id.in_(sorted(so_ids)))
                    .filter(models.Exposure.created_at <= as_of)
                    .all()
                ]
            )

        if po_ids:
            exposure_ids.update(
                [
                    e.id
                    for e in db.query(models.Exposure)
                    .filter(models.Exposure.source_type == models.MarketObjectType.po)
                    .filter(models.Exposure.source_id.in_(sorted(po_ids)))
                    .filter(models.Exposure.created_at <= as_of)
                    .all()
                ]
            )

        if hedge_ids:
            rfq_ids.update(
                [
                    r.id
                    for r in db.query(models.Rfq)
                    .filter(models.Rfq.hedge_id.in_(sorted(hedge_ids)))
                    .filter(models.Rfq.created_at <= as_of)
                    .all()
                ]
            )
            exposure_ids.update(
                [
                    he.exposure_id
                    for he in db.query(models.HedgeExposure)
                    .filter(models.HedgeExposure.hedge_id.in_(sorted(hedge_ids)))
                    .all()
                ]
            )

    rows: list[dict[str, str]] = []

    # Entities (payloads)
    if deal_ids:
        deals = (
            db.query(models.Deal)
            .filter(models.Deal.id.in_(sorted(deal_ids)))
            .filter(models.Deal.created_at <= as_of)
            .all()
        )
        for d in sorted(deals, key=lambda x: x.id):
            rows.append(
                _entity_row(
                    entity_type="deal",
                    entity_id=str(d.id),
                    payload={
                        "id": d.id,
                        "deal_uuid": d.deal_uuid,
                        "commodity": d.commodity,
                        "currency": d.currency,
                        "status": getattr(d.status, "value", str(d.status)),
                        "lifecycle_status": getattr(
                            d.lifecycle_status, "value", str(d.lifecycle_status)
                        ),
                        "created_at": _dt_iso(d.created_at),
                    },
                )
            )

    if so_ids:
        sos = (
            db.query(models.SalesOrder)
            .filter(models.SalesOrder.id.in_(sorted(so_ids)))
            .filter(models.SalesOrder.created_at <= as_of)
            .all()
        )
        for so in sorted(sos, key=lambda x: x.id):
            rows.append(
                _entity_row(
                    entity_type="sales_order",
                    entity_id=str(so.id),
                    payload={
                        "id": so.id,
                        "so_number": so.so_number,
                        "deal_id": so.deal_id,
                        "customer_id": so.customer_id,
                        "product": so.product,
                        "total_quantity_mt": so.total_quantity_mt,
                        "pricing_type": getattr(so.pricing_type, "value", str(so.pricing_type)),
                        "status": getattr(so.status, "value", str(so.status)),
                        "created_at": _dt_iso(so.created_at),
                    },
                )
            )
            if so.deal_id is not None:
                rows.append(
                    _relation_row(
                        from_type="sales_order",
                        from_id=str(so.id),
                        relation="belongs_to",
                        to_type="deal",
                        to_id=str(so.deal_id),
                    )
                )

    if po_ids:
        pos = (
            db.query(models.PurchaseOrder)
            .filter(models.PurchaseOrder.id.in_(sorted(po_ids)))
            .filter(models.PurchaseOrder.created_at <= as_of)
            .all()
        )
        for po in sorted(pos, key=lambda x: x.id):
            rows.append(
                _entity_row(
                    entity_type="purchase_order",
                    entity_id=str(po.id),
                    payload={
                        "id": po.id,
                        "po_number": po.po_number,
                        "deal_id": po.deal_id,
                        "supplier_id": po.supplier_id,
                        "product": po.product,
                        "total_quantity_mt": po.total_quantity_mt,
                        "pricing_type": getattr(po.pricing_type, "value", str(po.pricing_type)),
                        "status": getattr(po.status, "value", str(po.status)),
                        "created_at": _dt_iso(po.created_at),
                    },
                )
            )
            if po.deal_id is not None:
                rows.append(
                    _relation_row(
                        from_type="purchase_order",
                        from_id=str(po.id),
                        relation="belongs_to",
                        to_type="deal",
                        to_id=str(po.deal_id),
                    )
                )

    if rfq_ids:
        rfqs = (
            db.query(models.Rfq)
            .filter(models.Rfq.id.in_(sorted(rfq_ids)))
            .filter(models.Rfq.created_at <= as_of)
            .all()
        )
        for r in sorted(rfqs, key=lambda x: x.id):
            rows.append(
                _entity_row(
                    entity_type="rfq",
                    entity_id=str(r.id),
                    payload={
                        "id": r.id,
                        "rfq_number": r.rfq_number,
                        "deal_id": r.deal_id,
                        "so_id": r.so_id,
                        "quantity_mt": r.quantity_mt,
                        "period": r.period,
                        "status": getattr(r.status, "value", str(r.status)),
                        "institutional_state": getattr(
                            r.institutional_state, "value", str(r.institutional_state)
                        ),
                        "sent_at": _dt_iso(r.sent_at),
                        "awarded_at": _dt_iso(r.awarded_at),
                        "hedge_id": r.hedge_id,
                        "created_at": _dt_iso(r.created_at),
                    },
                )
            )
            if r.deal_id is not None:
                rows.append(
                    _relation_row(
                        from_type="rfq",
                        from_id=str(r.id),
                        relation="belongs_to",
                        to_type="deal",
                        to_id=str(r.deal_id),
                    )
                )
            rows.append(
                _relation_row(
                    from_type="rfq",
                    from_id=str(r.id),
                    relation="uses",
                    to_type="sales_order",
                    to_id=str(r.so_id),
                )
            )
            if r.hedge_id is not None:
                rows.append(
                    _relation_row(
                        from_type="rfq",
                        from_id=str(r.id),
                        relation="references",
                        to_type="hedge",
                        to_id=str(r.hedge_id),
                    )
                )

    if contract_ids:
        contracts = (
            db.query(models.Contract)
            .filter(models.Contract.contract_id.in_(sorted(contract_ids)))
            .filter(models.Contract.created_at <= as_of)
            .all()
        )
        for c in sorted(contracts, key=lambda x: x.contract_id):
            rows.append(
                _entity_row(
                    entity_type="contract",
                    entity_id=str(c.contract_id),
                    payload={
                        "contract_id": c.contract_id,
                        "deal_id": c.deal_id,
                        "rfq_id": c.rfq_id,
                        "counterparty_id": c.counterparty_id,
                        "status": c.status,
                        "trade_index": c.trade_index,
                        "quote_group_id": c.quote_group_id,
                        "settlement_date": (
                            c.settlement_date.isoformat() if c.settlement_date else None
                        ),
                        "created_at": _dt_iso(c.created_at),
                    },
                )
            )
            rows.append(
                _relation_row(
                    from_type="contract",
                    from_id=str(c.contract_id),
                    relation="belongs_to",
                    to_type="deal",
                    to_id=str(c.deal_id),
                )
            )
            rows.append(
                _relation_row(
                    from_type="contract",
                    from_id=str(c.contract_id),
                    relation="originated_from",
                    to_type="rfq",
                    to_id=str(c.rfq_id),
                )
            )

        # Contract exposures (join table)
        links = (
            db.query(models.ContractExposure)
            .filter(models.ContractExposure.contract_id.in_(sorted(contract_ids)))
            .filter(models.ContractExposure.created_at <= as_of)
            .all()
        )
        for ce in sorted(links, key=lambda x: (x.contract_id, x.exposure_id)):
            rows.append(
                _relation_row(
                    from_type="contract",
                    from_id=str(ce.contract_id),
                    relation="allocates",
                    to_type="exposure",
                    to_id=str(ce.exposure_id),
                    payload={"quantity_mt": ce.quantity_mt},
                )
            )

    if exposure_ids:
        exposures = (
            db.query(models.Exposure)
            .filter(models.Exposure.id.in_(sorted(exposure_ids)))
            .filter(models.Exposure.created_at <= as_of)
            .all()
        )
        for e in sorted(exposures, key=lambda x: x.id):
            rows.append(
                _entity_row(
                    entity_type="exposure",
                    entity_id=str(e.id),
                    payload={
                        "id": e.id,
                        "source_type": getattr(e.source_type, "value", str(e.source_type)),
                        "source_id": e.source_id,
                        "exposure_type": getattr(e.exposure_type, "value", str(e.exposure_type)),
                        "quantity_mt": e.quantity_mt,
                        "product": e.product,
                        "status": getattr(e.status, "value", str(e.status)),
                        "created_at": _dt_iso(e.created_at),
                    },
                )
            )
            rows.append(
                _relation_row(
                    from_type="exposure",
                    from_id=str(e.id),
                    relation="sourced_from",
                    to_type=getattr(e.source_type, "value", str(e.source_type)),
                    to_id=str(e.source_id),
                )
            )

    if hedge_ids:
        hedges = (
            db.query(models.Hedge)
            .filter(models.Hedge.id.in_(sorted(hedge_ids)))
            .filter(models.Hedge.created_at <= as_of)
            .all()
        )
        for h in sorted(hedges, key=lambda x: x.id):
            rows.append(
                _entity_row(
                    entity_type="hedge",
                    entity_id=str(h.id),
                    payload={
                        "id": h.id,
                        "so_id": h.so_id,
                        "counterparty_id": h.counterparty_id,
                        "quantity_mt": h.quantity_mt,
                        "contract_price": h.contract_price,
                        "current_market_price": h.current_market_price,
                        "mtm_value": h.mtm_value,
                        "period": h.period,
                        "status": getattr(h.status, "value", str(h.status)),
                        "created_at": _dt_iso(h.created_at),
                    },
                )
            )
            if h.so_id is not None:
                rows.append(
                    _relation_row(
                        from_type="hedge",
                        from_id=str(h.id),
                        relation="covers",
                        to_type="sales_order",
                        to_id=str(h.so_id),
                    )
                )

        # Hedge exposures (join table)
        links = (
            db.query(models.HedgeExposure)
            .filter(models.HedgeExposure.hedge_id.in_(sorted(hedge_ids)))
            .all()
        )
        for he in sorted(links, key=lambda x: (x.hedge_id, x.exposure_id)):
            rows.append(
                _relation_row(
                    from_type="hedge",
                    from_id=str(he.hedge_id),
                    relation="allocates",
                    to_type="exposure",
                    to_id=str(he.exposure_id),
                    payload={"quantity_mt": he.quantity_mt},
                )
            )

    # Deal links (entity relationships)
    if deal_ids:
        deal_links = (
            db.query(models.DealLink)
            .filter(models.DealLink.deal_id.in_(sorted(deal_ids)))
            .filter(models.DealLink.created_at <= as_of)
            .all()
        )
        for dl in sorted(deal_links, key=lambda x: (x.deal_id, x.id)):
            rows.append(
                _relation_row(
                    from_type="deal",
                    from_id=str(dl.deal_id),
                    relation="links_to",
                    to_type=getattr(dl.entity_type, "value", str(dl.entity_type)),
                    to_id=str(dl.entity_id),
                    payload={
                        "direction": getattr(dl.direction, "value", str(dl.direction)),
                        "quantity_mt": dl.quantity_mt,
                        "allocation_type": getattr(
                            dl.allocation_type, "value", str(dl.allocation_type)
                        ),
                    },
                )
            )

    # PnL snapshots (if available)
    if contract_ids:
        pnl = (
            db.query(models.PnlContractSnapshot)
            .filter(models.PnlContractSnapshot.contract_id.in_(sorted(contract_ids)))
            .all()
        )
        for p in sorted(pnl, key=lambda x: (x.as_of_date, x.id)):
            rows.append(
                _entity_row(
                    entity_type="pnl_contract_snapshot",
                    entity_id=str(p.id),
                    payload={
                        "id": p.id,
                        "contract_id": p.contract_id,
                        "deal_id": p.deal_id,
                        "as_of_date": p.as_of_date.isoformat(),
                        "currency": p.currency,
                        "unrealized_pnl_usd": p.unrealized_pnl_usd,
                        "methodology": p.methodology,
                        "data_quality_flags": p.data_quality_flags,
                        "inputs_hash": p.inputs_hash,
                        "created_at": _dt_iso(p.created_at),
                    },
                )
            )
            rows.append(
                _relation_row(
                    from_type="pnl_contract_snapshot",
                    from_id=str(p.id),
                    relation="summarizes",
                    to_type="contract",
                    to_id=str(p.contract_id),
                )
            )

    # MTM contract-only snapshots (if available)
    if contract_ids:
        cutoff_date = as_of.date()
        mtm_snapshots = (
            db.query(models.MtmContractSnapshot)
            .filter(models.MtmContractSnapshot.contract_id.in_(sorted(contract_ids)))
            .filter(models.MtmContractSnapshot.as_of_date == cutoff_date)
            .all()
        )
        for m in sorted(mtm_snapshots, key=lambda x: (x.as_of_date, x.id)):
            rows.append(
                _entity_row(
                    entity_type="mtm_contract_snapshot",
                    entity_id=str(m.id),
                    payload={
                        "id": m.id,
                        "run_id": m.run_id,
                        "contract_id": m.contract_id,
                        "deal_id": m.deal_id,
                        "as_of_date": m.as_of_date.isoformat(),
                        "currency": m.currency,
                        "mtm_usd": m.mtm_usd,
                        "methodology": m.methodology,
                        "references": m.references,
                        "inputs_hash": m.inputs_hash,
                        "created_at": _dt_iso(m.created_at),
                    },
                )
            )
            rows.append(
                _relation_row(
                    from_type="mtm_contract_snapshot",
                    from_id=str(m.id),
                    relation="summarizes",
                    to_type="contract",
                    to_id=str(m.contract_id),
                )
            )
            rows.append(
                _relation_row(
                    from_type="mtm_contract_snapshot",
                    from_id=str(m.id),
                    relation="belongs_to",
                    to_type="mtm_contract_snapshot_run",
                    to_id=str(m.run_id),
                )
            )

        if mtm_snapshots:
            run_ids = sorted({int(m.run_id) for m in mtm_snapshots})
            runs = db.query(models.MtmContractSnapshotRun).filter(
                models.MtmContractSnapshotRun.id.in_(run_ids)
            )
            for r in sorted(runs.all(), key=lambda x: x.id):
                rows.append(
                    _entity_row(
                        entity_type="mtm_contract_snapshot_run",
                        entity_id=str(r.id),
                        payload={
                            "id": r.id,
                            "as_of_date": r.as_of_date.isoformat(),
                            "scope_filters": r.scope_filters,
                            "inputs_hash": r.inputs_hash,
                            "requested_by_user_id": r.requested_by_user_id,
                            "created_at": _dt_iso(r.created_at),
                        },
                    )
                )

    # Cashflow baseline items (if available)
    if contract_ids:
        cutoff_date = as_of.date()
        cf_items = (
            db.query(models.CashflowBaselineItem)
            .filter(models.CashflowBaselineItem.contract_id.in_(sorted(contract_ids)))
            .filter(models.CashflowBaselineItem.as_of_date == cutoff_date)
            .all()
        )
        for cfi in sorted(cf_items, key=lambda x: (x.as_of_date, x.id)):
            rows.append(
                _entity_row(
                    entity_type="cashflow_baseline_item",
                    entity_id=str(cfi.id),
                    payload={
                        "id": cfi.id,
                        "run_id": cfi.run_id,
                        "as_of_date": cfi.as_of_date.isoformat(),
                        "contract_id": cfi.contract_id,
                        "deal_id": cfi.deal_id,
                        "rfq_id": cfi.rfq_id,
                        "counterparty_id": cfi.counterparty_id,
                        "settlement_date": (
                            cfi.settlement_date.isoformat() if cfi.settlement_date else None
                        ),
                        "currency": cfi.currency,
                        "projected_value_usd": cfi.projected_value_usd,
                        "projected_methodology": cfi.projected_methodology,
                        "projected_as_of": (
                            cfi.projected_as_of.isoformat() if cfi.projected_as_of else None
                        ),
                        "final_value_usd": cfi.final_value_usd,
                        "final_methodology": cfi.final_methodology,
                        "observation_start": (
                            cfi.observation_start.isoformat() if cfi.observation_start else None
                        ),
                        "observation_end_used": (
                            cfi.observation_end_used.isoformat()
                            if cfi.observation_end_used
                            else None
                        ),
                        "last_published_cash_date": (
                            cfi.last_published_cash_date.isoformat()
                            if cfi.last_published_cash_date
                            else None
                        ),
                        "data_quality_flags": cfi.data_quality_flags,
                        "references": cfi.references,
                        "inputs_hash": cfi.inputs_hash,
                        "created_at": _dt_iso(cfi.created_at),
                    },
                )
            )
            rows.append(
                _relation_row(
                    from_type="cashflow_baseline_item",
                    from_id=str(cfi.id),
                    relation="summarizes",
                    to_type="contract",
                    to_id=str(cfi.contract_id),
                )
            )
            rows.append(
                _relation_row(
                    from_type="cashflow_baseline_item",
                    from_id=str(cfi.id),
                    relation="originated_from",
                    to_type="rfq",
                    to_id=str(cfi.rfq_id),
                )
            )
            rows.append(
                _relation_row(
                    from_type="cashflow_baseline_item",
                    from_id=str(cfi.id),
                    relation="belongs_to",
                    to_type="cashflow_baseline_run",
                    to_id=str(cfi.run_id),
                )
            )

        if cf_items:
            run_ids = sorted({int(cfi.run_id) for cfi in cf_items})
            runs = db.query(models.CashflowBaselineRun).filter(
                models.CashflowBaselineRun.id.in_(run_ids)
            )
            for r in sorted(runs.all(), key=lambda x: x.id):
                rows.append(
                    _entity_row(
                        entity_type="cashflow_baseline_run",
                        entity_id=str(r.id),
                        payload={
                            "id": r.id,
                            "as_of_date": r.as_of_date.isoformat(),
                            "scope_filters": r.scope_filters,
                            "inputs_hash": r.inputs_hash,
                            "requested_by_user_id": r.requested_by_user_id,
                            "created_at": _dt_iso(r.created_at),
                        },
                    )
                )

    # Audit logs (linked to RFQs) up to as_of
    if rfq_ids:
        audit_logs = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.rfq_id.in_(sorted(rfq_ids)))
            .filter(models.AuditLog.created_at <= as_of)
            .all()
        )
        for al in sorted(audit_logs, key=lambda x: x.id):
            rows.append(
                _entity_row(
                    entity_type="audit_log",
                    entity_id=str(al.id),
                    payload={
                        "id": al.id,
                        "action": al.action,
                        "user_id": al.user_id,
                        "rfq_id": al.rfq_id,
                        "payload_json": al.payload_json,
                        "request_id": al.request_id,
                        "ip": al.ip,
                        "user_agent": al.user_agent,
                        "created_at": _dt_iso(al.created_at),
                    },
                )
            )
            if al.rfq_id is not None:
                rows.append(
                    _relation_row(
                        from_type="audit_log",
                        from_id=str(al.id),
                        relation="records",
                        to_type="rfq",
                        to_id=str(al.rfq_id),
                    )
                )

    # Deterministic sort of rows
    def _row_key(r: dict[str, str]) -> tuple:
        if r.get("record_type") == "entity":
            return (
                0,
                r.get("entity_type", ""),
                r.get("entity_id", ""),
                r.get("payload_json", ""),
            )
        return (
            1,
            r.get("from_type", ""),
            r.get("from_id", ""),
            r.get("relation", ""),
            r.get("to_type", ""),
            r.get("to_id", ""),
            r.get("payload_json", ""),
        )

    return sorted(rows, key=_row_key)


def build_chain_export_csv_bytes(
    db: Session,
    *,
    as_of: datetime,
    filters: dict[str, Any] | None,
) -> bytes:
    rows = build_chain_export_rows(db, as_of=as_of, filters=filters)

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "record_type",
            "entity_type",
            "entity_id",
            "from_type",
            "from_id",
            "relation",
            "to_type",
            "to_id",
            "payload_json",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

    return buf.getvalue().encode("utf-8")


def build_chain_export_pdf_bytes(
    db: Session,
    *,
    export_id: str,
    inputs_hash: str,
    as_of: datetime,
    filters: dict[str, Any] | None,
) -> bytes:
    rows = build_chain_export_rows(db, as_of=as_of, filters=filters)

    entity_count = sum(1 for r in rows if r.get("record_type") == "entity")
    relation_count = sum(1 for r in rows if r.get("record_type") == "relation")

    # Include a stable small sample of entities for auditing.
    sample_entities = [
        f"{r.get('entity_type')}:{r.get('entity_id')}"
        for r in rows
        if r.get("record_type") == "entity"
    ][:15]

    build_version = settings.build_version

    lines: list[str] = [
        "== Capa ==",
        "Chain Export (Institutional)",
        "",
        "== Metadados ==",
        f"export_id: {export_id}",
        f"inputs_hash: {inputs_hash}",
        "export_type: chain_export",
        f"as_of: {as_of.isoformat()}",
        f"gerado_em: {as_of.isoformat()}",
        f"build_version: {build_version}",
        "",
        "== Escopo ==",
        f"filters: {_canonical_json(filters or {})}",
        "",
        "== Resumo ==",
        f"entities: {entity_count}",
        f"relations: {relation_count}",
    ]

    if sample_entities:
        lines.append("Sample entities:")
        lines.extend([f"- {s}" for s in sample_entities])

    footer_lines = [
        f"export_id={export_id}",
        f"inputs_hash={inputs_hash}",
        f"as_of={as_of.isoformat()}",
    ]

    if build_version:
        footer_lines.append(f"build_version={build_version}")

    return build_simple_text_pdf_bytes(
        title="Chain Export (Institutional)",
        lines=lines,
        footer_lines=footer_lines,
    )


def build_chain_export_package_bytes(
    db: Session,
    *,
    export_id: str,
    inputs_hash: str,
    as_of: datetime,
    filters: dict[str, Any] | None,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Return (zip_bytes, csv_bytes, pdf_bytes, manifest_bytes)."""

    csv_bytes = build_chain_export_csv_bytes(db, as_of=as_of, filters=filters)
    pdf_bytes = build_chain_export_pdf_bytes(
        db,
        export_id=export_id,
        inputs_hash=inputs_hash,
        as_of=as_of,
        filters=filters,
    )

    # Build manifest with checksums computed over the *embedded* bytes.
    def _sha256(b: bytes) -> str:
        import hashlib

        return hashlib.sha256(b).hexdigest()

    build_version = settings.build_version

    manifest = {
        "schema_version": 1,
        "export_id": export_id,
        "inputs_hash": inputs_hash,
        "export_type": "chain_export",
        "as_of": as_of.isoformat() if as_of else None,
        # Deterministic: use the snapshot cutoff as the generation timestamp.
        "gerado_em": as_of.isoformat() if as_of else None,
        "filters": filters or {},
        "versoes": {
            "build_version": build_version,
            "export_schema_version": 1,
        },
        "artifacts": [
            {
                "filename": "chain_export.csv",
                "content_type": "text/csv",
                "size_bytes": len(csv_bytes),
                "checksum_sha256": _sha256(csv_bytes),
            },
            {
                "filename": "chain_export.pdf",
                "content_type": "application/pdf",
                "size_bytes": len(pdf_bytes),
                "checksum_sha256": _sha256(pdf_bytes),
            },
        ],
    }

    manifest_bytes = _canonical_json(manifest).encode("utf-8")

    zip_bytes = _deterministic_zip_bytes(
        [
            ("manifest.json", manifest_bytes),
            ("chain_export.csv", csv_bytes),
            ("chain_export.pdf", pdf_bytes),
        ]
    )

    return zip_bytes, csv_bytes, pdf_bytes, manifest_bytes
