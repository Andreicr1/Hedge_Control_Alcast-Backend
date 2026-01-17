from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

THRESHOLD_USD = 250_000.0
SLA_HOURS_DEFAULT = 24


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm_money(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        d = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return format(d, "f")


@dataclass(frozen=True)
class WorkflowPolicyResult:
    requires_approval: bool
    required_role: str | None
    threshold_usd: float | None
    notional_usd: float | None


def approval_policy_for_action(*, action: str, notional_usd: float | None) -> WorkflowPolicyResult:
    """T3 v0: approvals are required for the two gated actions.

    Required role is decided by a single threshold. If notional can't be computed,
    default to requires_admin for safety.
    """

    if action not in {"rfq.award", "hedge.manual.create"}:
        return WorkflowPolicyResult(
            requires_approval=False,
            required_role=None,
            threshold_usd=None,
            notional_usd=notional_usd,
        )

    if notional_usd is None:
        return WorkflowPolicyResult(
            requires_approval=True,
            required_role=models.RoleName.admin.value,
            threshold_usd=THRESHOLD_USD,
            notional_usd=None,
        )

    required = (
        models.RoleName.financeiro.value
        if notional_usd < THRESHOLD_USD
        else models.RoleName.admin.value
    )
    return WorkflowPolicyResult(
        requires_approval=True,
        required_role=required,
        threshold_usd=THRESHOLD_USD,
        notional_usd=notional_usd,
    )


def compute_workflow_inputs_hash(
    *,
    action: str,
    subject_type: str,
    subject_id: str,
    required_role: str,
    notional_usd: float | None,
    threshold_usd: float | None,
    context: dict[str, Any] | None,
) -> str:
    payload: dict[str, Any] = {
        "action": action,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "required_role": required_role,
        "notional_usd": _norm_money(notional_usd),
        "threshold_usd": _norm_money(threshold_usd),
        "context": context or {},
    }
    return _sha256_hex(_canonical_json(payload))


def get_or_create_workflow_request(
    *,
    db: Session,
    action: str,
    subject_type: str,
    subject_id: str,
    required_role: str,
    notional_usd: float | None,
    threshold_usd: float | None,
    context: dict[str, Any] | None,
    requested_by_user_id: int | None,
    correlation_id: str | None,
    sla_hours: int = SLA_HOURS_DEFAULT,
) -> tuple[models.WorkflowRequest, bool]:
    inputs_hash = compute_workflow_inputs_hash(
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        required_role=required_role,
        notional_usd=notional_usd,
        threshold_usd=threshold_usd,
        context=context,
    )
    request_key = f"wf_{inputs_hash[:32]}"

    existing = (
        db.query(models.WorkflowRequest)
        .filter(models.WorkflowRequest.request_key == request_key)
        .first()
    )
    if existing is not None:
        return existing, True

    due_at = datetime.utcnow() + timedelta(hours=int(sla_hours or SLA_HOURS_DEFAULT))

    wf = models.WorkflowRequest(
        request_key=request_key,
        inputs_hash=inputs_hash,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        status="pending",
        notional_usd=notional_usd,
        threshold_usd=threshold_usd,
        required_role=required_role,
        context=context or {},
        requested_by_user_id=requested_by_user_id,
        sla_due_at=due_at,
        correlation_id=correlation_id,
    )

    db.add(wf)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.WorkflowRequest)
            .filter(models.WorkflowRequest.request_key == request_key)
            .first()
        )
        if existing is None:
            raise
        return existing, True

    db.refresh(wf)
    return wf, False


def _http_approval_required(*, wf: models.WorkflowRequest) -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "approval_required",
            "workflow_request_id": wf.id,
            "request_key": wf.request_key,
            "status": wf.status,
            "action": wf.action,
            "subject_type": wf.subject_type,
            "subject_id": wf.subject_id,
            "required_role": wf.required_role,
            "threshold_usd": wf.threshold_usd,
            "notional_usd": wf.notional_usd,
        },
    )


def _emit_workflow_requested(
    *,
    db: Session,
    wf: models.WorkflowRequest,
    request_id: str | None,
    ip: str | None,
    user_agent: str | None,
    actor_user_id: int | None,
) -> None:
    # Import lazily to avoid circular imports at module import-time.
    from app.services.audit import audit_event
    from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

    idem = f"workflow_request:{wf.request_key}:requested"

    audit_id = audit_event(
        "workflow.requested",
        actor_user_id,
        {
            "workflow_request_id": wf.id,
            "request_key": wf.request_key,
            "inputs_hash": wf.inputs_hash,
            "action": wf.action,
            "subject_type": wf.subject_type,
            "subject_id": wf.subject_id,
            "required_role": wf.required_role,
            "threshold_usd": wf.threshold_usd,
            "notional_usd": wf.notional_usd,
        },
        db=db,
        idempotency_key=idem,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
    )

    emit_timeline_event(
        db=db,
        event_type="WORKFLOW_REQUESTED",
        subject_type="workflow",
        subject_id=int(wf.id),
        correlation_id=str(wf.correlation_id or correlation_id_from_request_id(request_id)),
        idempotency_key=idem,
        visibility="finance",
        actor_user_id=actor_user_id,
        audit_log_id=audit_id,
        payload={
            "workflow_request_id": wf.id,
            "request_key": wf.request_key,
            "action": wf.action,
            "subject_type": wf.subject_type,
            "subject_id": wf.subject_id,
            "required_role": wf.required_role,
            "threshold_usd": wf.threshold_usd,
            "notional_usd": wf.notional_usd,
        },
    )


def _emit_workflow_executed(
    *,
    db: Session,
    wf: models.WorkflowRequest,
    request_id: str | None,
    ip: str | None,
    user_agent: str | None,
    actor_user_id: int | None,
) -> None:
    from app.services.audit import audit_event
    from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

    idem = f"workflow_request:{wf.request_key}:executed"

    audit_id = audit_event(
        "workflow.executed",
        actor_user_id,
        {
            "workflow_request_id": wf.id,
            "request_key": wf.request_key,
            "action": wf.action,
            "subject_type": wf.subject_type,
            "subject_id": wf.subject_id,
        },
        db=db,
        idempotency_key=idem,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
    )

    emit_timeline_event(
        db=db,
        event_type="WORKFLOW_EXECUTED",
        subject_type="workflow",
        subject_id=int(wf.id),
        correlation_id=str(wf.correlation_id or correlation_id_from_request_id(request_id)),
        idempotency_key=idem,
        visibility="finance",
        actor_user_id=actor_user_id,
        audit_log_id=audit_id,
        payload={
            "workflow_request_id": wf.id,
            "request_key": wf.request_key,
            "action": wf.action,
            "subject_type": wf.subject_type,
            "subject_id": wf.subject_id,
        },
    )


def require_approval_or_raise(
    *,
    db: Session,
    action: str,
    subject_type: str,
    subject_id: str,
    notional_usd: float | None,
    context: dict[str, Any] | None,
    requested_by_user_id: int | None,
    correlation_id: str | None,
    workflow_request_id: int | None,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> models.WorkflowRequest | None:
    policy = approval_policy_for_action(action=action, notional_usd=notional_usd)
    if not policy.requires_approval:
        return None

    assert policy.required_role is not None

    if workflow_request_id is None:
        wf, _idempotent = get_or_create_workflow_request(
            db=db,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            required_role=policy.required_role,
            notional_usd=policy.notional_usd,
            threshold_usd=policy.threshold_usd,
            context=context,
            requested_by_user_id=requested_by_user_id,
            correlation_id=correlation_id,
        )

        _emit_workflow_requested(
            db=db,
            wf=wf,
            request_id=request_id,
            ip=ip,
            user_agent=user_agent,
            actor_user_id=requested_by_user_id,
        )
        _http_approval_required(wf=wf)

    wf = db.get(models.WorkflowRequest, int(workflow_request_id))
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow request not found")
    if wf.action != action or wf.subject_type != subject_type or wf.subject_id != subject_id:
        raise HTTPException(status_code=409, detail={"code": "workflow_request_mismatch"})
    if wf.status != "approved":
        _http_approval_required(wf=wf)

    return wf


def mark_workflow_executed(
    *,
    db: Session,
    workflow_request_id: int,
    executed_by_user_id: int | None,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> models.WorkflowRequest:
    wf = db.get(models.WorkflowRequest, int(workflow_request_id))
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow request not found")

    if wf.status == "executed":
        return wf

    if wf.status != "approved":
        raise HTTPException(status_code=409, detail="Workflow request is not approved")

    wf.status = "executed"
    wf.executed_at = datetime.utcnow()
    wf.executed_by_user_id = executed_by_user_id
    db.add(wf)
    db.commit()
    db.refresh(wf)

    _emit_workflow_executed(
        db=db,
        wf=wf,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        actor_user_id=executed_by_user_id,
    )
    return wf
