from __future__ import annotations

# ruff: noqa: B008
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.workflows import (
    WorkflowDecisionCreate,
    WorkflowDecisionRead,
    WorkflowRequestRead,
)
from app.services.audit import audit_event
from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

router = APIRouter(prefix="/workflows", tags=["workflows"])

_workflows_read_roles_dep = require_roles(
    models.RoleName.financeiro,
    models.RoleName.admin,
    models.RoleName.auditoria,
)
_workflows_decide_roles_dep = require_roles(models.RoleName.financeiro, models.RoleName.admin)


@router.get("/requests", response_model=list[WorkflowRequestRead])
def list_workflow_requests(
    status_filter: Optional[str] = Query(None, alias="status"),  # noqa: B008
    action: Optional[str] = Query(None),  # noqa: B008
    required_role: Optional[str] = Query(None),  # noqa: B008
    limit: int = Query(50, ge=1, le=200),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(_workflows_read_roles_dep),  # noqa: B008
):
    q = db.query(models.WorkflowRequest).options(selectinload(models.WorkflowRequest.decisions))

    if status_filter:
        q = q.filter(models.WorkflowRequest.status == status_filter)
    if action:
        q = q.filter(models.WorkflowRequest.action == action)
    if required_role:
        q = q.filter(models.WorkflowRequest.required_role == required_role)

    return q.order_by(models.WorkflowRequest.requested_at.desc()).limit(limit).all()


@router.get("/requests/{workflow_request_id}", response_model=WorkflowRequestRead)
def get_workflow_request(
    workflow_request_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(_workflows_read_roles_dep),  # noqa: B008
):
    wf = (
        db.query(models.WorkflowRequest)
        .options(selectinload(models.WorkflowRequest.decisions))
        .filter(models.WorkflowRequest.id == workflow_request_id)
        .first()
    )
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow request not found")
    return wf


@router.post(
    "/requests/{workflow_request_id}/decisions",
    response_model=WorkflowDecisionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow_decision(
    workflow_request_id: int,
    payload: WorkflowDecisionCreate,
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: models.User = Depends(_workflows_decide_roles_dep),  # noqa: B008
):
    wf = db.get(models.WorkflowRequest, workflow_request_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow request not found")

    # RBAC matrix: required_role=admin => only admin can decide.
    required = (wf.required_role or "").lower()
    if required == models.RoleName.admin.value and (
        not getattr(current_user, "role", None)
        or getattr(current_user.role, "name", None) != models.RoleName.admin
    ):
        raise HTTPException(status_code=403, detail="Insufficient role for decision")

    now = datetime.utcnow()
    new_status: Literal["approved", "rejected"] = (
        "approved" if payload.decision == "approved" else "rejected"
    )

    # Idempotent replay support: if already decided with same outcome, return existing decision.
    if wf.status != "pending":
        if wf.status == new_status:
            existing = (
                db.query(models.WorkflowDecision)
                .filter(models.WorkflowDecision.workflow_request_id == workflow_request_id)
                .filter(models.WorkflowDecision.decision == new_status)
                .order_by(models.WorkflowDecision.id.desc())
                .first()
            )
            if existing is not None:
                return existing
        raise HTTPException(status_code=409, detail="Workflow request is not pending")

    # Atomic guard: only the first decision wins.
    updated = (
        db.query(models.WorkflowRequest)
        .filter(
            and_(
                models.WorkflowRequest.id == workflow_request_id,
                models.WorkflowRequest.status == "pending",
            )
        )
        .update({"status": new_status, "decided_at": now})
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Workflow request status changed")

    decision_idempotency_key = f"wf_decision:{workflow_request_id}:{new_status}"

    d = models.WorkflowDecision(
        workflow_request_id=workflow_request_id,
        decision=new_status,
        justification=payload.justification,
        decided_by_user_id=getattr(current_user, "id", None),
        decided_at=now,
        idempotency_key=decision_idempotency_key,
    )
    db.add(d)

    try:
        db.commit()
        db.refresh(d)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.WorkflowDecision)
            .filter(models.WorkflowDecision.idempotency_key == decision_idempotency_key)
            .order_by(models.WorkflowDecision.id.desc())
            .first()
        )
        if existing is None:
            raise
        d = existing

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    audit_event(
        "workflow.decision.created",
        getattr(current_user, "id", None),
        {
            "workflow_request_id": workflow_request_id,
            "decision": new_status,
            "action": wf.action,
            "subject_type": wf.subject_type,
            "subject_id": wf.subject_id,
        },
        db=db,
        idempotency_key=f"workflow:{workflow_request_id}:decision:{new_status}",
        request_id=request.headers.get("X-Request-ID"),
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("User-Agent"),
    )

    emit_timeline_event(
        db=db,
        event_type="WORKFLOW_APPROVED" if new_status == "approved" else "WORKFLOW_REJECTED",
        subject_type="workflow",
        subject_id=int(workflow_request_id),
        correlation_id=correlation_id,
        idempotency_key=f"workflow:{workflow_request_id}:{new_status}",
        visibility="finance",
        actor_user_id=getattr(current_user, "id", None),
        payload={
            "workflow_request_id": workflow_request_id,
            "decision": new_status,
            "action": wf.action,
            "subject_type": wf.subject_type,
            "subject_id": wf.subject_id,
            "required_role": wf.required_role,
        },
    )

    return d
