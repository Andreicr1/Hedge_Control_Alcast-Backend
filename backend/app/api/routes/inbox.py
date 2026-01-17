import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, selectinload

from app import models
from app.api.deps import get_current_user, require_roles
from app.database import get_db
from app.schemas.exposures import ExposureRead
from app.schemas.inbox import (
    InboxCounts,
    InboxDecisionCreate,
    InboxDecisionRead,
    InboxNetExposureRow,
    InboxWorkbenchResponse,
)
from app.services.exposure_aggregation import compute_net_exposure
from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

router = APIRouter(
    prefix="/inbox",
    tags=["inbox"],
)


@router.get("/counts", response_model=InboxCounts)
def inbox_counts(
    db: Session = Depends(get_db),
    _user: models.User = Depends(
        require_roles(models.RoleName.financeiro, models.RoleName.admin, models.RoleName.auditoria)
    ),
):
    exposures_active = (
        db.query(models.Exposure)
        .filter(
            models.Exposure.status == models.ExposureStatus.open,
            models.Exposure.exposure_type == models.ExposureType.active,
        )
        .count()
    )
    exposures_passive = (
        db.query(models.Exposure)
        .filter(
            models.Exposure.status == models.ExposureStatus.open,
            models.Exposure.exposure_type == models.ExposureType.passive,
        )
        .count()
    )
    exposures_residual = (
        db.query(models.Exposure)
        .filter(models.Exposure.status == models.ExposureStatus.partially_hedged)
        .count()
    )

    return InboxCounts(
        purchase_orders_pending=db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.status == models.OrderStatus.active)
        .count(),
        sales_orders_pending=db.query(models.SalesOrder)
        .filter(models.SalesOrder.status == models.OrderStatus.active)
        .count(),
        rfqs_draft=db.query(models.Rfq).filter(models.Rfq.status == models.RfqStatus.draft).count(),
        rfqs_sent=db.query(models.Rfq).filter(models.Rfq.status == models.RfqStatus.sent).count(),
        exposures_active=exposures_active,
        exposures_passive=exposures_passive,
        exposures_residual=exposures_residual,
    )


@router.get("/workbench", response_model=InboxWorkbenchResponse)
def inbox_workbench(
    db: Session = Depends(get_db),
    _user: models.User = Depends(
        require_roles(models.RoleName.financeiro, models.RoleName.admin, models.RoleName.auditoria)
    ),
):
    """Financeiro Workbench (Inbox): a view over Exposure + summary metrics.

    Guardrails:
    - Inbox is a view (no workflow engine)
    - Exposure is the source of truth
    """

    counts = inbox_counts(db=db)

    exposures_q = (
        db.query(models.Exposure)
        .options(selectinload(models.Exposure.tasks))
        .filter(
            models.Exposure.status.in_(
                [models.ExposureStatus.open, models.ExposureStatus.partially_hedged]
            )
        )
        .order_by(models.Exposure.id.desc())
    )
    exposures = exposures_q.all()

    active = [
        e
        for e in exposures
        if e.status == models.ExposureStatus.open and e.exposure_type == models.ExposureType.active
    ]
    passive = [
        e
        for e in exposures
        if e.status == models.ExposureStatus.open and e.exposure_type == models.ExposureType.passive
    ]
    residual = [e for e in exposures if e.status == models.ExposureStatus.partially_hedged]

    net_rows = compute_net_exposure(db)
    net_exposure = [
        InboxNetExposureRow(
            product=r.product,
            period=r.period,
            gross_active=r.gross_active,
            gross_passive=r.gross_passive,
            hedged=r.hedged,
            net=r.net,
        )
        for r in net_rows
    ]

    return InboxWorkbenchResponse(
        counts=counts,
        net_exposure=net_exposure,
        active=[ExposureRead.from_orm(e) for e in active],
        passive=[ExposureRead.from_orm(e) for e in passive],
        residual=[ExposureRead.from_orm(e) for e in residual],
    )


@router.get("/exposures/{exposure_id}", response_model=ExposureRead)
def inbox_exposure_detail(
    exposure_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(
        require_roles(models.RoleName.financeiro, models.RoleName.admin, models.RoleName.auditoria)
    ),
):
    exposure = (
        db.query(models.Exposure)
        .options(selectinload(models.Exposure.tasks))
        .filter(models.Exposure.id == exposure_id)
        .first()
    )
    if not exposure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exposure not found")
    return ExposureRead.from_orm(exposure)


@router.get("/exposures/{exposure_id}/decisions", response_model=list[InboxDecisionRead])
def inbox_list_decisions(
    exposure_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(
        require_roles(models.RoleName.financeiro, models.RoleName.admin, models.RoleName.auditoria)
    ),
):
    """List audit-only decisions for an exposure.

    Note: decisions are stored as AuditLog entries (action + payload_json).
    """

    logs = (
        db.query(models.AuditLog)
        .filter(models.AuditLog.action == "inbox.decision.no_hedge")
        .order_by(models.AuditLog.id.desc())
        .all()
    )

    out: list[InboxDecisionRead] = []
    for log in logs:
        try:
            payload = json.loads(log.payload_json or "{}")
        except Exception:
            payload = {}
        if payload.get("exposure_id") != exposure_id:
            continue
        out.append(
            InboxDecisionRead(
                id=log.id,
                decision="no_hedge",
                justification=str(payload.get("justification") or ""),
                created_at=log.created_at,
                created_by_user_id=log.user_id,
            )
        )
    return out


@router.post("/exposures/{exposure_id}/decisions", response_model=InboxDecisionRead)
def inbox_create_decision(
    exposure_id: int,
    data: InboxDecisionCreate,
    request: Request,
    db: Session = Depends(get_db),
    _role_guard: models.User = Depends(require_roles(models.RoleName.financeiro)),
    user: models.User = Depends(get_current_user),
):
    """Create an audit-only decision.

    Guardrails (critical): MUST NOT mutate Exposure status or create RFQs/Contracts.
    """

    exposure = db.query(models.Exposure).filter(models.Exposure.id == exposure_id).first()
    if not exposure:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exposure not found")

    if data.decision != "no_hedge":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported decision")

    payload = {
        "exposure_id": exposure_id,
        "decision": data.decision,
        "justification": data.justification,
    }

    log = models.AuditLog(
        action="inbox.decision.no_hedge",
        user_id=user.id,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))
    emit_timeline_event(
        db=db,
        event_type="INBOX_DECISION_RECORDED",
        subject_type="exposure",
        subject_id=int(exposure_id),
        correlation_id=correlation_id,
        idempotency_key=f"inbox_decision:{log.id}:recorded",
        visibility="finance",
        actor_user_id=getattr(user, "id", None),
        audit_log_id=log.id,
        payload={
            "exposure_id": exposure_id,
            "decision": data.decision,
            "justification": data.justification,
            "audit_log_id": log.id,
        },
    )

    return InboxDecisionRead(
        id=log.id,
        decision="no_hedge",
        justification=data.justification,
        created_at=log.created_at,
        created_by_user_id=log.user_id,
    )
