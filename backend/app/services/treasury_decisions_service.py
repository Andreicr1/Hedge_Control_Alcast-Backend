from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models


@dataclass(frozen=True)
class TreasuryKycGateResult:
    allowed: bool
    reason_code: str | None = None
    details: dict[str, Any] | None = None


def _resolve_supplier_kyc_gate(*, db: Session, supplier_id: int) -> TreasuryKycGateResult:
    supplier = db.get(models.Supplier, supplier_id)
    if not supplier:
        return TreasuryKycGateResult(allowed=False, reason_code="SUPPLIER_NOT_FOUND")

    kyc_status = (getattr(supplier, "kyc_status", None) or "").strip().lower() or None
    if kyc_status != "approved":
        return TreasuryKycGateResult(
            allowed=False,
            reason_code="SUPPLIER_KYC_STATUS_NOT_APPROVED",
            details={"kyc_status": getattr(supplier, "kyc_status", None)},
        )

    if bool(getattr(supplier, "sanctions_flag", False)):
        return TreasuryKycGateResult(allowed=False, reason_code="SUPPLIER_SANCTIONS_FLAGGED")

    risk_rating = (getattr(supplier, "risk_rating", None) or "").strip().lower()
    if risk_rating in {"high", "very_high", "critical"}:
        return TreasuryKycGateResult(
            allowed=False,
            reason_code="SUPPLIER_RISK_RATING_BLOCKED",
            details={"risk_rating": getattr(supplier, "risk_rating", None)},
        )

    return TreasuryKycGateResult(allowed=True)


def resolve_exposure_kyc_gate(*, db: Session, exposure: models.Exposure) -> TreasuryKycGateResult:
    """Non-blocking KYC resolver for Treasury Decisions.

    Institutional rule:
    - Decision must never be blocked due to KYC.
    - We still compute a deterministic KYC gate outcome and persist it for auditability.
    """

    if exposure.source_type == models.MarketObjectType.so:
        from app.services.so_kyc_gate import resolve_so_kyc_gate

        res = resolve_so_kyc_gate(db=db, so_id=int(exposure.source_id))
        return TreasuryKycGateResult(
            allowed=res.allowed, reason_code=res.reason_code, details=res.details
        )

    if exposure.source_type == models.MarketObjectType.po:
        po = db.get(models.PurchaseOrder, int(exposure.source_id))
        if not po:
            return TreasuryKycGateResult(allowed=False, reason_code="PO_NOT_FOUND")
        return _resolve_supplier_kyc_gate(db=db, supplier_id=int(po.supplier_id))

    # Default: unknown source type; treat as "cannot evaluate".
    return TreasuryKycGateResult(allowed=False, reason_code="EXPOSURE_SOURCE_TYPE_UNSUPPORTED")


def create_treasury_decision(
    *,
    db: Session,
    exposure_id: int,
    decision_kind: models.TreasuryDecisionKind,
    notes: str | None,
    decided_at: datetime | None,
    actor_user_id: int | None,
    request_id: str | None,
    ip: str | None,
    user_agent: str | None,
) -> models.TreasuryDecision:
    exposure = db.get(models.Exposure, int(exposure_id))
    if not exposure:
        raise ValueError("exposure_not_found")

    gate = resolve_exposure_kyc_gate(db=db, exposure=exposure)
    gate_json = {
        "allowed": gate.allowed,
        "reason_code": gate.reason_code,
        "details": gate.details,
        "evaluated_at": datetime.utcnow().isoformat(),
    }

    td = models.TreasuryDecision(
        exposure_id=int(exposure_id),
        decision_kind=decision_kind,
        decided_at=decided_at or datetime.utcnow(),
        notes=notes,
        kyc_gate_json=gate_json,
        created_by_user_id=actor_user_id,
    )

    db.add(td)
    db.commit()
    db.refresh(td)

    from app.services.audit import audit_event
    from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

    idem = f"treasury_decision:{td.id}:created"

    audit_id = audit_event(
        "treasury_decision.created",
        actor_user_id,
        {
            "treasury_decision_id": td.id,
            "exposure_id": td.exposure_id,
            "decision_kind": td.decision_kind.value
            if isinstance(td.decision_kind, models.TreasuryDecisionKind)
            else str(td.decision_kind),
            "decided_at": td.decided_at.isoformat() if td.decided_at else None,
            "kyc_gate": gate_json,
        },
        db=db,
        idempotency_key=idem,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
    )

    emit_timeline_event(
        db=db,
        event_type="TREASURY_DECISION_CREATED",
        subject_type="exposure",
        subject_id=int(td.exposure_id),
        correlation_id=correlation_id_from_request_id(request_id),
        idempotency_key=idem,
        visibility="finance",
        actor_user_id=actor_user_id,
        audit_log_id=audit_id,
        payload={
            "treasury_decision_id": td.id,
            "exposure_id": td.exposure_id,
            "decision_kind": td.decision_kind.value
            if isinstance(td.decision_kind, models.TreasuryDecisionKind)
            else str(td.decision_kind),
            "kyc_allowed": gate.allowed,
            "kyc_reason_code": gate.reason_code,
        },
    )

    return td


def list_treasury_decisions(
    *, db: Session, exposure_id: int | None = None
) -> list[models.TreasuryDecision]:
    q = db.query(models.TreasuryDecision)
    if exposure_id is not None:
        q = q.filter(models.TreasuryDecision.exposure_id == int(exposure_id))
    return q.order_by(models.TreasuryDecision.id.desc()).all()


def get_treasury_decision(*, db: Session, decision_id: int) -> models.TreasuryDecision | None:
    return db.get(models.TreasuryDecision, int(decision_id))


def create_kyc_override(
    *,
    db: Session,
    decision: models.TreasuryDecision,
    reason: str,
    actor_user_id: int | None,
    request_id: str | None,
    ip: str | None,
    user_agent: str | None,
) -> models.TreasuryKycOverride:
    snapshot = {
        "treasury_decision_id": decision.id,
        "exposure_id": decision.exposure_id,
        "decision_kind": decision.decision_kind.value
        if isinstance(decision.decision_kind, models.TreasuryDecisionKind)
        else str(decision.decision_kind),
        "kyc_gate": decision.kyc_gate_json,
        "recorded_at": datetime.utcnow().isoformat(),
    }

    ov = models.TreasuryKycOverride(
        decision_id=int(decision.id),
        reason=reason,
        snapshot_json=snapshot,
        created_by_user_id=actor_user_id,
    )

    db.add(ov)
    try:
        db.commit()
        db.refresh(ov)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.TreasuryKycOverride)
            .filter(models.TreasuryKycOverride.decision_id == int(decision.id))
            .first()
        )
        if existing is None:
            raise
        ov = existing

    from app.services.audit import audit_event
    from app.services.timeline_emitters import correlation_id_from_request_id, emit_timeline_event

    idem = f"treasury_decision:{decision.id}:kyc_override"

    audit_id = audit_event(
        "treasury_decision.kyc_override_created",
        actor_user_id,
        {
            "treasury_decision_id": decision.id,
            "treasury_kyc_override_id": ov.id,
            "exposure_id": decision.exposure_id,
            "reason": reason,
        },
        db=db,
        idempotency_key=idem,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
    )

    emit_timeline_event(
        db=db,
        event_type="TREASURY_KYC_OVERRIDE_CREATED",
        subject_type="exposure",
        subject_id=int(decision.exposure_id),
        correlation_id=correlation_id_from_request_id(request_id),
        idempotency_key=idem,
        visibility="finance",
        actor_user_id=actor_user_id,
        audit_log_id=audit_id,
        payload={
            "treasury_decision_id": decision.id,
            "treasury_kyc_override_id": ov.id,
            "exposure_id": decision.exposure_id,
        },
    )

    return ov
