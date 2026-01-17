import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, selectinload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import RfqAttemptReport, RfqExportItem, RfqReportItem

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/rfq-by-counterparty",
    response_model=List[RfqReportItem],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def rfq_by_counterparty(
    db: Session = Depends(get_db),
    counterparty: Optional[str] = Query(None, description="Filter by provider name (counterparty)"),
    status: Optional[models.RfqStatus] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    query = db.query(models.RfqQuote)
    if counterparty:
        query = query.filter(models.RfqQuote.provider == counterparty)
    if status:
        query = query.join(models.Rfq, models.RfqQuote.rfq_id == models.Rfq.id).filter(
            models.Rfq.status == status
        )
    if start_date:
        query = query.filter(models.RfqQuote.created_at >= start_date)
    if end_date:
        query = query.filter(models.RfqQuote.created_at <= end_date)

    quotes = query.all()
    report_items: List[RfqReportItem] = []
    for q in quotes:
        report_items.append(
            RfqReportItem(
                rfq_id=q.rfq_id,
                quote_id=q.id,
                provider=q.provider,
                price=q.price,
                fee_bps=q.fee_bps,
                currency=q.currency,
                created_at=q.created_at,
                selected=q.selected,
            )
        )
    return report_items


@router.get(
    "/rfq-attempts",
    response_model=List[RfqAttemptReport],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def rfq_attempts(
    db: Session = Depends(get_db),
    counterparty: Optional[str] = Query(None),
    status: Optional[models.SendStatus] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
):
    query = db.query(models.RfqSendAttempt).join(
        models.Rfq, models.RfqSendAttempt.rfq_id == models.Rfq.id
    )
    if status:
        query = query.filter(models.RfqSendAttempt.status == status)
    if start_date:
        query = query.filter(models.RfqSendAttempt.created_at >= start_date)
    if end_date:
        query = query.filter(models.RfqSendAttempt.created_at <= end_date)
    attempts = query.all()
    items: List[RfqAttemptReport] = []
    for att in attempts:
        meta = {}
        if att.metadata_json:
            import json

            try:
                meta = json.loads(att.metadata_json)
            except json.JSONDecodeError:
                meta = {}
        cp_name = meta.get("counterparty_name")
        if counterparty and cp_name != counterparty:
            continue
        items.append(
            RfqAttemptReport(
                rfq_id=att.rfq_id,
                attempt_id=att.id,
                channel=att.channel,
                status=att.status.value if hasattr(att.status, "value") else str(att.status),
                provider_message_id=att.provider_message_id,
                counterparty_name=cp_name,
                created_at=att.created_at,
            )
        )
    return items


@router.get(
    "/rfq-export",
    response_model=List[RfqExportItem],
    dependencies=[Depends(require_roles(models.RoleName.admin, models.RoleName.financeiro))],
)
def rfq_export(
    db: Session = Depends(get_db),
    counterparty: Optional[str] = Query(None, description="Filter by counterparty/provider name"),
    rfq_status: Optional[models.RfqStatus] = Query(None),
    attempt_status: Optional[models.SendStatus] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    format: str = Query("json", description="json or csv"),
):
    rfq_query = (
        db.query(models.Rfq)
        .options(selectinload(models.Rfq.send_attempts), selectinload(models.Rfq.quotes))
        .order_by(models.Rfq.created_at.desc())
    )
    if rfq_status:
        rfq_query = rfq_query.filter(models.Rfq.status == rfq_status)
    if start_date:
        rfq_query = rfq_query.filter(models.Rfq.created_at >= start_date)
    if end_date:
        rfq_query = rfq_query.filter(models.Rfq.created_at <= end_date)

    rfqs = rfq_query.all()
    rows: List[RfqExportItem] = []

    for rfq in rfqs:
        providers: set[str] = set()
        for att in rfq.send_attempts:
            meta_name = (att.metadata_dict or {}).get("counterparty_name")
            providers.add(meta_name or "")
        for quote in rfq.quotes:
            providers.add(quote.provider or "")
        if not providers:
            providers.add("")

        for provider in providers:
            attempts_for_provider = [
                att
                for att in rfq.send_attempts
                if (att.metadata_dict or {}).get("counterparty_name", "") == provider
            ]
            quotes_for_provider = [q for q in rfq.quotes if (q.provider or "") == provider]

            attempt = (
                sorted(attempts_for_provider, key=lambda a: a.created_at, reverse=True)[0]
                if attempts_for_provider
                else None
            )
            quote = (
                sorted(quotes_for_provider, key=lambda q: q.created_at, reverse=True)[0]
                if quotes_for_provider
                else None
            )

            if counterparty and provider != counterparty:
                continue
            if attempt_status:
                if not attempt or attempt.status != attempt_status:
                    continue

            row_time = (
                quote.created_at if quote else (attempt.created_at if attempt else rfq.created_at)
            )
            if start_date and row_time and row_time < start_date:
                continue
            if end_date and row_time and row_time > end_date:
                continue

            rows.append(
                RfqExportItem(
                    rfq_id=rfq.id,
                    rfq_status=rfq.status.value
                    if hasattr(rfq.status, "value")
                    else str(rfq.status),
                    rfq_channel=rfq.channel,
                    rfq_created_at=rfq.created_at,
                    provider=provider or None,
                    attempt_status=attempt.status.value if attempt else None,
                    attempt_channel=attempt.channel if attempt else None,
                    attempt_created_at=attempt.created_at if attempt else None,
                    quote_id=quote.id if quote else None,
                    quote_price=quote.price if quote else None,
                    quote_fee_bps=quote.fee_bps if quote else None,
                    quote_currency=quote.currency if quote else None,
                    quote_selected=quote.selected if quote else None,
                )
            )

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "rfq_id",
                "rfq_status",
                "rfq_channel",
                "rfq_created_at",
                "provider",
                "attempt_status",
                "attempt_channel",
                "attempt_created_at",
                "quote_id",
                "quote_price",
                "quote_fee_bps",
                "quote_currency",
                "quote_selected",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.rfq_id,
                    row.rfq_status,
                    row.rfq_channel,
                    row.rfq_created_at.isoformat() if row.rfq_created_at else "",
                    row.provider or "",
                    row.attempt_status or "",
                    row.attempt_channel or "",
                    row.attempt_created_at.isoformat() if row.attempt_created_at else "",
                    row.quote_id or "",
                    row.quote_price or "",
                    row.quote_fee_bps or "",
                    row.quote_currency or "",
                    row.quote_selected if row.quote_selected is not None else "",
                ]
            )
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=rfq_export.csv"},
        )

    return rows
