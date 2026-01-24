# ruff: noqa: B008, E501

import logging
import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session, noload, selectinload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.models.domain import RfqStatus
from app.schemas import (
    RfqAwardRequest,
    RfqCreate,
    RfqQuoteCreate,
    RfqQuoteRead,
    RfqRead,
    RfqUpdate,
)
from app.services import rfq_engine
from app.services.audit import audit_event
from app.services.document_numbering import next_monthly_number
from app.services.rfq_message_builder import build_rfq_message
from app.services.rfq_state_timeline import emit_rfq_state_changed
from app.services.rfq_transitions import atomic_transition_rfq_status, coalesce_datetime
from app.services.so_kyc_gate import resolve_so_kyc_gate
from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event
from app.services.workflow_approvals import mark_workflow_executed, require_approval_or_raise

router = APIRouter(prefix="/rfqs", tags=["rfqs"])
logger = logging.getLogger("alcast.rfqs")


def _exposure_period_bucket(exposure: models.Exposure) -> str:
    if exposure.delivery_date:
        return exposure.delivery_date.strftime("%Y-%m")
    if exposure.sale_date:
        return exposure.sale_date.strftime("%Y-%m")
    if exposure.payment_date:
        return exposure.payment_date.strftime("%Y-%m")
    return "unknown"


def _trade_quantity_mt(*, trade_snapshot: dict, fallback: float) -> float:
    legs = (trade_snapshot or {}).get("legs") or []
    for leg in legs:
        try:
            v = leg.get("volume_mt")
            if v is not None:
                return float(v)
        except Exception:
            continue
    return float(fallback)


def _link_contract_to_exposures(
    *,
    db: Session,
    contract: models.Contract,
    deal_id: int,
    rfq_period: str,
) -> None:
    allowed_types = (models.PriceType.AVG, models.PriceType.AVG_INTER, models.PriceType.C2R)
    # Candidate exposures: open (or partially hedged), floating, belonging to this deal.
    so_exposures = (
        db.query(models.Exposure)
        .join(models.SalesOrder, models.SalesOrder.id == models.Exposure.source_id)
        .filter(models.Exposure.source_type == models.MarketObjectType.so)
        .filter(models.SalesOrder.deal_id == int(deal_id))
        .filter(models.SalesOrder.pricing_type.in_(allowed_types))
        .filter(models.Exposure.status != models.ExposureStatus.closed)
        .all()
    )
    po_exposures = (
        db.query(models.Exposure)
        .join(models.PurchaseOrder, models.PurchaseOrder.id == models.Exposure.source_id)
        .filter(models.Exposure.source_type == models.MarketObjectType.po)
        .filter(models.PurchaseOrder.deal_id == int(deal_id))
        .filter(models.PurchaseOrder.pricing_type.in_(allowed_types))
        .filter(models.Exposure.status != models.ExposureStatus.closed)
        .all()
    )
    exposures = [
        e for e in (so_exposures + po_exposures) if _exposure_period_bucket(e) == rfq_period
    ]
    exposures.sort(
        key=lambda e: (
            getattr(e.source_type, "value", str(e.source_type)),
            int(e.source_id),
            int(e.id),
        )
    )

    if not exposures:
        return

    exposure_ids = [int(e.id) for e in exposures]

    # Compute already allocated volumes (hedge_exposures + contract_exposures) so we don't over-allocate.
    existing_contract_alloc = dict(
        db.query(
            models.ContractExposure.exposure_id,
            func.coalesce(func.sum(models.ContractExposure.quantity_mt), 0.0),
        )
        .filter(models.ContractExposure.exposure_id.in_(exposure_ids))
        .group_by(models.ContractExposure.exposure_id)
        .all()
    )
    existing_hedge_alloc = dict(
        db.query(
            models.HedgeExposure.exposure_id,
            func.coalesce(func.sum(models.HedgeExposure.quantity_mt), 0.0),
        )
        .filter(models.HedgeExposure.exposure_id.in_(exposure_ids))
        .group_by(models.HedgeExposure.exposure_id)
        .all()
    )

    remaining_qty = _trade_quantity_mt(
        trade_snapshot=contract.trade_snapshot or {},
        fallback=float(
            getattr(db.get(models.Rfq, int(contract.rfq_id)), "quantity_mt", 0.0) or 0.0
        ),
    )
    if remaining_qty <= 0:
        return

    for exp in exposures:
        exp_id = int(exp.id)
        allocated = float(existing_contract_alloc.get(exp_id, 0.0)) + float(
            existing_hedge_alloc.get(exp_id, 0.0)
        )
        exp_remaining = float(exp.quantity_mt or 0.0) - allocated
        if exp_remaining <= 1e-9:
            continue

        take = min(float(remaining_qty), float(exp_remaining))
        if take <= 1e-9:
            continue

        db.add(
            models.ContractExposure(
                contract_id=str(contract.contract_id),
                exposure_id=exp_id,
                quantity_mt=float(take),
            )
        )
        remaining_qty -= take
        if remaining_qty <= 1e-9:
            break


def _group_trades(quotes: list[models.RfqQuote]) -> list[dict]:
    grouped: dict[str, list[models.RfqQuote]] = {}
    for idx, q in enumerate(quotes):
        key = q.quote_group_id or f"q-{q.id or idx}"
        grouped.setdefault(key, []).append(q)

    trades: list[dict] = []
    for idx, (gid, legs) in enumerate(grouped.items()):
        buy = next((leg for leg in legs if (leg.leg_side or "").lower() == "buy"), None)
        sell = next((leg for leg in legs if (leg.leg_side or "").lower() == "sell"), None)
        if not buy or not sell:
            raise HTTPException(
                status_code=400,
                detail=f"Cotação incompleta para trade {gid}: é necessário buy e sell",
            )
        if buy.volume_mt and sell.volume_mt and abs(buy.volume_mt - sell.volume_mt) > 1e-6:
            raise HTTPException(status_code=400, detail=f"Volumes divergentes no trade {gid}")
        trades.append(
            {
                "trade_index": idx,
                "quote_group_id": gid,
                "legs": [
                    {
                        "quote_id": buy.id,
                        "side": "buy",
                        "price": buy.quote_price,
                        "volume_mt": buy.volume_mt,
                        "price_type": buy.price_type,
                        "valid_until": buy.valid_until.isoformat() if buy.valid_until else None,
                        "notes": buy.notes,
                    },
                    {
                        "quote_id": sell.id,
                        "side": "sell",
                        "price": sell.quote_price,
                        "volume_mt": sell.volume_mt,
                        "price_type": sell.price_type,
                        "valid_until": sell.valid_until.isoformat() if sell.valid_until else None,
                        "notes": sell.notes,
                    },
                ],
            }
        )
    return trades


@router.get("", response_model=List[RfqRead])
def list_rfqs(
    limit: int = Query(int(os.getenv("RFQS_LIST_DEFAULT_LIMIT", "50")), ge=1, le=200),
    offset: int = Query(0, ge=0),
    expand: str | None = Query(None, description="Expand: quotes,invitations"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.financeiro, models.RoleName.auditoria)
    ),
):
    """List RFQs with pagination.

    Default payload excludes quotes and invitations. Use ?expand=quotes,invitations
    to include them.
    """
    max_limit = int(os.getenv("RFQS_LIST_MAX_LIMIT", "200"))
    safe_limit = min(int(limit), max_limit)

    env_default_expand = os.getenv("RFQS_LIST_DEFAULT_EXPAND", "")
    expand_value = ",".join([v for v in [env_default_expand, expand or ""] if v])
    expand_set = {e.strip().lower() for e in expand_value.split(",") if e.strip()}
    include_quotes = "quotes" in expand_set
    include_invitations = "invitations" in expand_set

    q = db.query(models.Rfq).options(
        noload(models.Rfq.counterparty_quotes),
        noload(models.Rfq.invitations),
    )

    if include_quotes:
        q = q.options(selectinload(models.Rfq.counterparty_quotes))
    if include_invitations:
        q = q.options(selectinload(models.Rfq.invitations))

    rfqs = q.order_by(models.Rfq.created_at.desc()).offset(int(offset)).limit(safe_limit).all()

    return rfqs


@router.post("", response_model=RfqRead, status_code=status.HTTP_201_CREATED)
def create_rfq(
    request: Request,
    payload: RfqCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    so = db.get(models.SalesOrder, payload.so_id)
    if not so:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sales Order not found")

    if getattr(payload, "deal_id", None) is not None:
        deal = db.get(models.Deal, int(payload.deal_id))
        if not deal:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal not found")
        if so.deal_id is not None and int(so.deal_id) != int(payload.deal_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sales Order belongs to a different deal",
            )
        if so.deal_id is None:
            so.deal_id = int(payload.deal_id)
            db.add(so)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    rfq_number = payload.rfq_number
    if not rfq_number:
        rfq_number = next_monthly_number(db, doc_type="RFQ", prefix="RFQ").formatted

    gate = resolve_so_kyc_gate(db=db, so_id=payload.so_id)
    if not gate.allowed:
        audit_event(
            "kyc.gate.blocked_rfq_create",
            getattr(current_user, "id", None),
            {
                "so_id": payload.so_id,
                "rfq_number": rfq_number,
                "customer_id": gate.customer_id,
                "customer_kyc_status": gate.customer_kyc_status,
                "reason_code": gate.reason_code,
                "details": gate.details,
            },
            db=db,
            request_id=request.headers.get("X-Request-ID"),
            ip=(request.client.host if request.client else None),
            user_agent=request.headers.get("User-Agent"),
        )

        emit_timeline_event(
            db=db,
            event_type="KYC_GATE_BLOCKED",
            subject_type="so",
            subject_id=int(payload.so_id),
            correlation_id=correlation_id,
            idempotency_key=f"kyc_gate:block:rfq_create:{payload.so_id}:{rfq_number}",
            visibility="finance",
            actor_user_id=getattr(current_user, "id", None),
            payload={
                "blocked_action": "rfq_create",
                "so_id": payload.so_id,
                "rfq_number": rfq_number,
                "customer_id": gate.customer_id,
                "customer_kyc_status": gate.customer_kyc_status,
                "reason_code": gate.reason_code,
                "details": gate.details,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": gate.reason_code,
                "so_id": payload.so_id,
                "customer_id": gate.customer_id,
                "details": gate.details,
            },
        )

    rfq = models.Rfq(
        rfq_number=rfq_number,
        so_id=payload.so_id,
        quantity_mt=payload.quantity_mt,
        period=payload.period,
        status=payload.status,
        message_text=payload.message_text,
        trade_specs=payload.trade_specs,
    )
    if getattr(payload, "deal_id", None) is not None:
        rfq.deal_id = int(payload.deal_id)
    elif so.deal_id:
        rfq.deal_id = int(so.deal_id)
    if not getattr(rfq, "deal_id", None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFQ must be linked to a deal",
        )
    if payload.invitations:
        for inv in payload.invitations:
            cp = db.get(models.Counterparty, inv.counterparty_id)
            invitation_message_text = None
            if cp:
                try:
                    invitation_message_text = build_rfq_message(rfq, cp)
                except Exception:
                    invitation_message_text = None
            rfq.invitations.append(
                models.RfqInvitation(
                    counterparty_id=inv.counterparty_id,
                    counterparty_name=inv.counterparty_name,
                    status=inv.status,
                    expires_at=inv.expires_at,
                    message_text=invitation_message_text,
                )
            )
    if payload.counterparty_quotes:
        for quote in payload.counterparty_quotes:
            rfq.counterparty_quotes.append(
                models.RfqQuote(
                    counterparty_id=quote.counterparty_id,
                    counterparty_name=quote.counterparty_name,
                    quote_price=quote.quote_price,
                    price_type=quote.price_type,
                    volume_mt=quote.volume_mt,
                    valid_until=quote.valid_until,
                    notes=quote.notes,
                    channel=quote.channel,
                    status=quote.status,
                    quote_group_id=quote.quote_group_id,
                    leg_side=quote.leg_side,
                )
            )

    db.add(rfq)
    db.commit()
    db.refresh(rfq)

    emit_timeline_event(
        db=db,
        event_type="RFQ_CREATED",
        subject_type="rfq",
        subject_id=int(rfq.id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq:{rfq.id}:created",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "rfq_id": rfq.id,
            "rfq_number": rfq.rfq_number,
            "so_id": rfq.so_id,
            "deal_id": rfq.deal_id,
            "invited_counterparty_ids": [
                inv.counterparty_id for inv in (rfq.invitations or []) if inv.counterparty_id
            ],
        },
    )

    logger.info("rfq.created", extra={"rfq_id": rfq.id, "rfq_number": rfq.rfq_number})
    return rfq


@router.get("/{rfq_id}", response_model=RfqRead)
def get_rfq(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.financeiro, models.RoleName.auditoria)
    ),
):
    rfq = (
        db.query(models.Rfq)
        .options(
            selectinload(models.Rfq.counterparty_quotes),
            selectinload(models.Rfq.invitations),
        )
        .filter(models.Rfq.id == rfq_id)
        .first()
    )
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    return rfq


@router.put("/{rfq_id}", response_model=RfqRead)
def update_rfq(
    rfq_id: int,
    payload: RfqUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status == RfqStatus.awarded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RFQ já encerrado; edição não permitida",
        )

    # Status transitions are guarded by dedicated endpoints.
    # Allowing status changes here increases the risk of invalid transitions.
    if payload.status is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use os endpoints dedicados para transições de status (send/award/cancel/quotes)",
        )

    data = payload.dict(exclude_unset=True, exclude={"counterparty_quotes"})
    for field, value in data.items():
        setattr(rfq, field, value)

    if payload.counterparty_quotes is not None:
        rfq.counterparty_quotes.clear()
        for quote in payload.counterparty_quotes:
            rfq.counterparty_quotes.append(
                models.RfqQuote(
                    counterparty_id=quote.counterparty_id,
                    counterparty_name=quote.counterparty_name,
                    quote_price=quote.quote_price,
                    price_type=quote.price_type,
                    volume_mt=quote.volume_mt,
                    valid_until=quote.valid_until,
                    notes=quote.notes,
                    channel=quote.channel,
                    status=quote.status,
                    quote_group_id=quote.quote_group_id,
                    leg_side=quote.leg_side,
                )
            )
    if payload.invitations is not None:
        rfq.invitations.clear()
        for inv in payload.invitations:
            cp = db.get(models.Counterparty, inv.counterparty_id)
            rfq.invitations.append(
                models.RfqInvitation(
                    counterparty_id=inv.counterparty_id,
                    counterparty_name=inv.counterparty_name,
                    status=inv.status,
                    expires_at=inv.expires_at,
                    message_text=build_rfq_message(rfq, cp) if cp else None,
                )
            )

    db.add(rfq)
    db.commit()
    db.refresh(rfq)
    return rfq


@router.post("/{rfq_id}/quotes", response_model=RfqQuoteRead, status_code=status.HTTP_201_CREATED)
def add_quote(
    rfq_id: int,
    payload: RfqQuoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    from_status = rfq.status
    if rfq.status in {RfqStatus.awarded, RfqStatus.failed, RfqStatus.expired}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ encerrado para novas cotações"
        )

    quote = models.RfqQuote(
        rfq_id=rfq_id,
        counterparty_id=payload.counterparty_id,
        counterparty_name=payload.counterparty_name,
        quote_price=payload.quote_price,
        price_type=payload.price_type,
        volume_mt=payload.volume_mt,
        valid_until=payload.valid_until,
        notes=payload.notes,
        channel=payload.channel,
        status=payload.status,
        quote_group_id=payload.quote_group_id,
        leg_side=payload.leg_side,
    )
    db.add(quote)
    # Atualiza convite correspondente, se existir
    if payload.counterparty_id:
        invitation = (
            db.query(models.RfqInvitation)
            .filter(
                models.RfqInvitation.rfq_id == rfq_id,
                models.RfqInvitation.counterparty_id == payload.counterparty_id,
            )
            .first()
        )
        if invitation:
            invitation.status = "answered"
            invitation.responded_at = quote.quoted_at
            db.add(invitation)

    transition = atomic_transition_rfq_status(
        db=db,
        rfq_id=rfq_id,
        to_status=RfqStatus.quoted,
        allowed_from={RfqStatus.draft, RfqStatus.pending, RfqStatus.sent, RfqStatus.quoted},
    )
    if not transition.updated:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RFQ status changed; quote not allowed"
        )

    db.commit()
    db.refresh(quote)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    if transition.updated and from_status != RfqStatus.quoted:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=RfqStatus.quoted,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
            reason="quote_created",
        )

    emit_timeline_event(
        db=db,
        event_type="RFQ_QUOTE_CREATED",
        subject_type="rfq",
        subject_id=int(rfq.id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq_quote:{quote.id}:created",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "rfq_id": rfq.id,
            "quote_id": quote.id,
            "counterparty_id": quote.counterparty_id,
            "counterparty_name": quote.counterparty_name,
            "quote_price": quote.quote_price,
            "price_type": quote.price_type,
            "volume_mt": quote.volume_mt,
            "channel": quote.channel,
            "status": quote.status,
        },
    )

    return quote


@router.post("/{rfq_id}/award", response_model=RfqRead)
def award_quote(
    rfq_id: int,
    payload: RfqAwardRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = (
        db.query(models.Rfq)
        .options(selectinload(models.Rfq.counterparty_quotes))
        .filter(models.Rfq.id == rfq_id)
        .first()
    )
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ não encontrado")
    from_status = rfq.status
    if rfq.status in {RfqStatus.awarded, RfqStatus.failed, RfqStatus.expired}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ já encerrado")
    if rfq.status not in {RfqStatus.quoted, RfqStatus.sent, RfqStatus.pending, RfqStatus.draft}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ não está pronta para decisão"
        )

    quote = next((q for q in rfq.counterparty_quotes if q.id == payload.quote_id), None)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cotação não encontrada neste RFQ"
        )

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    gate = resolve_so_kyc_gate(db=db, so_id=int(rfq.so_id))
    if not gate.allowed:
        audit_event(
            "kyc.gate.blocked_rfq_award",
            getattr(current_user, "id", None),
            {
                "so_id": rfq.so_id,
                "rfq_id": rfq_id,
                "quote_id": payload.quote_id,
                "customer_id": gate.customer_id,
                "customer_kyc_status": gate.customer_kyc_status,
                "reason_code": gate.reason_code,
                "details": gate.details,
            },
            db=db,
            request_id=request.headers.get("X-Request-ID"),
            ip=(request.client.host if request.client else None),
            user_agent=request.headers.get("User-Agent"),
        )

        emit_timeline_event(
            db=db,
            event_type="KYC_GATE_BLOCKED",
            subject_type="so",
            subject_id=int(rfq.so_id),
            correlation_id=correlation_id,
            idempotency_key=f"kyc_gate:block:contract_create:{rfq.so_id}:{rfq_id}:{payload.quote_id}",
            visibility="finance",
            actor_user_id=getattr(current_user, "id", None),
            payload={
                "blocked_action": "contract_create",
                "so_id": rfq.so_id,
                "rfq_id": rfq_id,
                "quote_id": payload.quote_id,
                "customer_id": gate.customer_id,
                "customer_kyc_status": gate.customer_kyc_status,
                "reason_code": gate.reason_code,
                "details": gate.details,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": gate.reason_code,
                "so_id": rfq.so_id,
                "customer_id": gate.customer_id,
                "details": gate.details,
            },
        )

    # T3 approval gating (no domain side-effects when approval is required).
    notional_usd: float | None = None
    try:
        if rfq.quantity_mt is not None and quote.quote_price is not None:
            notional_usd = float(rfq.quantity_mt) * float(quote.quote_price)
    except Exception:
        notional_usd = None

    wf = require_approval_or_raise(
        db=db,
        action="rfq.award",
        subject_type="rfq",
        subject_id=str(rfq.id),
        notional_usd=notional_usd,
        context={
            "rfq_id": rfq.id,
            "quote_id": payload.quote_id,
            "so_id": rfq.so_id,
            "rfq_number": rfq.rfq_number,
        },
        requested_by_user_id=getattr(current_user, "id", None),
        correlation_id=correlation_id,
        workflow_request_id=getattr(payload, "workflow_request_id", None),
        request_id=request.headers.get("X-Request-ID"),
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("User-Agent"),
    )

    # Ranking posição simples (menor preço vence; se precisar lado considerar campo futuro)
    sorted_quotes = sorted(rfq.counterparty_quotes, key=lambda q: q.quote_price)
    rank_position = next((idx + 1 for idx, q in enumerate(sorted_quotes) if q.id == quote.id), None)

    # Atomic guard: ensure only one award wins under concurrency.
    decided_at = datetime.utcnow()

    transition = atomic_transition_rfq_status(
        db=db,
        rfq_id=rfq_id,
        to_status=RfqStatus.awarded,
        allowed_from={RfqStatus.draft, RfqStatus.pending, RfqStatus.sent, RfqStatus.quoted},
        updates={
            "winner_quote_id": quote.id,
            "decision_reason": payload.motivo,
            "decided_by": current_user.id,
            "decided_at": decided_at,
            "awarded_at": coalesce_datetime(models.Rfq.awarded_at, decided_at),
            "winner_rank": rank_position,
            "hedge_id": payload.hedge_id,
            "hedge_reference": payload.hedge_reference,
        },
    )
    if not transition.updated:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RFQ status changed; award not allowed"
        )

    # Refresh ORM instance so later flushes don't clobber the atomic UPDATE.
    db.refresh(rfq)

    # Atualiza convites para status final
    for inv in rfq.invitations:
        if inv.counterparty_id == quote.counterparty_id:
            inv.status = "winner"
        else:
            inv.status = "lost" if inv.status not in {"expired", "refused"} else inv.status
        db.add(inv)

    db.add(rfq)
    # contratos: um por trade do vencedor
    winner_cp_id = quote.counterparty_id
    winner_quotes = [q for q in rfq.counterparty_quotes if q.counterparty_id == winner_cp_id]
    trades = _group_trades(winner_quotes)
    deal_id = rfq.deal_id or (rfq.sales_order.deal_id if rfq.sales_order else None)
    if not deal_id:
        raise HTTPException(
            status_code=400, detail="RFQ não possui deal associado para criar contratos"
        )
    created_contracts: list[models.Contract] = []
    for trade in trades:
        settlement_date = None
        settlement_meta = None
        try:
            idx = int(trade.get("trade_index") or 0)
            if getattr(rfq, "trade_specs", None) and idx < len(rfq.trade_specs):
                spec = rfq.trade_specs[idx]
                holidays = (spec or {}).get("holidays") or None
                cal = rfq_engine.HolidayCalendar(holidays)

                def _leg_from_spec(leg: dict) -> rfq_engine.Leg:
                    order = None
                    if leg.get("order"):
                        order = rfq_engine.OrderInstruction(
                            order_type=leg["order"]["order_type"],
                            validity=leg["order"].get("validity"),
                            limit_price=leg["order"].get("limit_price"),
                        )
                    return rfq_engine.Leg(
                        side=leg["side"],
                        price_type=leg["price_type"],
                        quantity_mt=float(leg.get("quantity_mt") or rfq.quantity_mt),
                        month_name=leg.get("month_name"),
                        year=leg.get("year"),
                        start_date=leg.get("start_date"),
                        end_date=leg.get("end_date"),
                        fixing_date=leg.get("fixing_date"),
                        ppt=leg.get("ppt"),
                        order=order,
                    )

                t = rfq_engine.RfqTrade(
                    trade_type=spec["trade_type"],
                    leg1=_leg_from_spec(spec["leg1"]),
                    leg2=_leg_from_spec(spec["leg2"]) if spec.get("leg2") else None,
                    sync_ppt=bool(spec.get("sync_ppt") or False),
                )
                ppt = rfq_engine.compute_trade_ppt_dates(t, cal=cal)
                settlement_date = ppt.get("trade_ppt")
                settlement_meta = {
                    "source": "rfq_engine",
                    "leg1_ppt": ppt.get("leg1_ppt").isoformat() if ppt.get("leg1_ppt") else None,
                    "leg2_ppt": ppt.get("leg2_ppt").isoformat() if ppt.get("leg2_ppt") else None,
                    "trade_ppt": ppt.get("trade_ppt").isoformat() if ppt.get("trade_ppt") else None,
                }
        except Exception:
            # If trade_specs are missing/malformed, keep settlement_date null; Contract still created.
            settlement_date = None
            settlement_meta = None

        if settlement_date:
            trade["settlement_date"] = settlement_date.isoformat()

        contract_number = next_monthly_number(db, doc_type="CT", prefix="CT").formatted
        contract = models.Contract(
            contract_number=contract_number,
            deal_id=deal_id,
            rfq_id=rfq.id,
            counterparty_id=winner_cp_id,
            status=models.ContractStatus.active.value,
            trade_index=trade.get("trade_index"),
            quote_group_id=trade.get("quote_group_id"),
            trade_snapshot=trade,
            settlement_date=settlement_date,
            settlement_meta=settlement_meta,
            created_by=current_user.id,
        )
        db.add(contract)
        created_contracts.append(contract)

    # Persist the contract → exposure links for traceability (PO vs SO origin).
    # Note: this does not change Exposure status; it is an audit-style linkage.
    for c in created_contracts:
        _link_contract_to_exposures(
            db=db, contract=c, deal_id=int(deal_id), rfq_period=str(rfq.period)
        )

    db.commit()
    logger.info(
        "rfq.awarded",
        extra={
            "rfq_id": rfq.id,
            "winner_quote_id": quote.id,
            "decided_by": current_user.id,
            "rank": rank_position,
        },
    )
    db.refresh(rfq)

    # Emit v1-compatible CONTRACT_CREATED per contract.
    for c in created_contracts:
        emit_timeline_event(
            db=db,
            event_type="CONTRACT_CREATED",
            subject_type="rfq",
            subject_id=int(rfq.id),
            correlation_id=correlation_id,
            idempotency_key=f"contract:{c.contract_id}:created",
            visibility="finance",
            actor_user_id=getattr(current_user, "id", None),
            payload={
                "contract_id": c.contract_id,
                "rfq_id": rfq.id,
                "deal_id": c.deal_id,
                "counterparty_id": c.counterparty_id,
                "settlement_date": c.settlement_date.isoformat() if c.settlement_date else None,
                "trade_index": c.trade_index,
                "quote_group_id": c.quote_group_id,
            },
        )

    emit_timeline_event(
        db=db,
        event_type="RFQ_AWARDED",
        subject_type="rfq",
        subject_id=int(rfq.id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq:{rfq.id}:awarded",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "rfq_id": rfq.id,
            "quote_id": quote.id,
            "decided_by_user_id": rfq.decided_by,
            "decided_at": rfq.decided_at.isoformat() if rfq.decided_at else None,
            "winner_rank": rfq.winner_rank,
            "hedge_id": rfq.hedge_id,
            "decision_reason": rfq.decision_reason,
            "award_source": "award_quote",
        },
    )

    if transition.updated and from_status != RfqStatus.awarded:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=RfqStatus.awarded,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
            reason="award",
        )

    if wf is not None:
        mark_workflow_executed(
            db=db,
            workflow_request_id=int(wf.id),
            executed_by_user_id=getattr(current_user, "id", None),
            request_id=request.headers.get("X-Request-ID"),
            ip=(request.client.host if request.client else None),
            user_agent=request.headers.get("User-Agent"),
        )

    return rfq


@router.post("/{rfq_id}/cancel", response_model=RfqRead)
def cancel_rfq(
    rfq_id: int,
    motivo: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    rfq = db.get(models.Rfq, rfq_id)
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ não encontrado")
    from_status = rfq.status
    if rfq.status in {RfqStatus.awarded, RfqStatus.failed, RfqStatus.expired}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ já encerrado")

    transition = atomic_transition_rfq_status(
        db=db,
        rfq_id=rfq_id,
        to_status=RfqStatus.failed,
        allowed_from={RfqStatus.draft, RfqStatus.pending, RfqStatus.sent, RfqStatus.quoted},
        updates={
            "decision_reason": motivo,
            "decided_by": current_user.id,
            "decided_at": datetime.utcnow(),
        },
    )
    if not transition.updated:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="RFQ status changed; cancel not allowed"
        )

    db.commit()
    db.refresh(rfq)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    if transition.updated and from_status != RfqStatus.failed:
        emit_rfq_state_changed(
            db=db,
            rfq_id=int(rfq.id),
            from_status=from_status,
            to_status=RfqStatus.failed,
            correlation_id=correlation_id,
            actor_user_id=getattr(current_user, "id", None),
            reason="cancel",
        )

    emit_timeline_event(
        db=db,
        event_type="RFQ_CANCELLED",
        subject_type="rfq",
        subject_id=int(rfq.id),
        correlation_id=correlation_id,
        idempotency_key=f"rfq:{rfq.id}:cancelled",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "rfq_id": rfq.id,
            "reason": motivo,
            "decided_by_user_id": rfq.decided_by,
            "decided_at": rfq.decided_at.isoformat() if rfq.decided_at else None,
        },
    )

    return rfq


@router.get("/{rfq_id}/quotes/export")
def export_quotes_csv(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.financeiro, models.RoleName.auditoria)
    ),
):
    rfq = (
        db.query(models.Rfq)
        .options(selectinload(models.Rfq.counterparty_quotes))
        .filter(models.Rfq.id == rfq_id)
        .first()
    )
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ não encontrado")

    rfq = (
        db.query(models.Rfq)
        .options(selectinload(models.Rfq.counterparty_quotes))
        .filter(models.Rfq.id == rfq_id)
        .first()
    )
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ não encontrado")

    def _csv_escape(value):
        s = (value or "").replace('"', '""')
        return f'"{s}"'

    rows = ["quote_id,counterparty,price,volume_mt,channel,status,quoted_at,notes"]

    for q in rfq.counterparty_quotes:
        rows.append(
            ",".join(
                [
                    str(q.id),
                    _csv_escape(q.counterparty_name),
                    str(q.quote_price or ""),
                    str(q.volume_mt or ""),
                    _csv_escape(q.channel),
                    q.status or "",
                    q.quoted_at.isoformat() if q.quoted_at else "",
                    _csv_escape(q.notes),
                ]
            )
        )

    csv_data = "\n".join(rows)

    headers = {"Content-Disposition": f'attachment; filename="rfq_{rfq_id}_quotes.csv"'}

    return Response(
        content=csv_data,
        media_type="text/csv",
        headers=headers,
    )
