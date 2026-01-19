from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.treasury_decisions import (
    TreasuryDecisionCreate,
    TreasuryDecisionListRead,
    TreasuryDecisionRead,
    TreasuryKycOverrideCreate,
)
from app.services.treasury_decisions_service import (
    create_kyc_override,
    create_treasury_decision,
    get_treasury_decision,
    list_treasury_decisions,
)

router = APIRouter(prefix="/treasury/decisions", tags=["treasury"])

_DB_DEP = Depends(get_db)


def _to_read_model(td: models.TreasuryDecision) -> TreasuryDecisionRead:
    gate = td.kyc_gate_json or None
    gate_obj = None
    if gate is not None:
        gate_obj = {
            "allowed": bool(gate.get("allowed")),
            "reason_code": gate.get("reason_code"),
            "details": gate.get("details"),
        }

    override_obj = None
    if td.kyc_override is not None:
        override_obj = {
            "id": td.kyc_override.id,
            "decision_id": td.kyc_override.decision_id,
            "reason": td.kyc_override.reason,
            "snapshot_json": td.kyc_override.snapshot_json,
            "created_by_user_id": td.kyc_override.created_by_user_id,
            "created_at": td.kyc_override.created_at,
        }

    kyc_allowed = None
    if gate is not None:
        kyc_allowed = bool(gate.get("allowed"))

    if kyc_allowed is True:
        kyc_state = "ok"
        kyc_requires_override = False
    elif override_obj is not None:
        kyc_state = "overridden"
        kyc_requires_override = False
    else:
        kyc_state = "needs_override"
        kyc_requires_override = True

    return TreasuryDecisionRead(
        id=td.id,
        exposure_id=td.exposure_id,
        decision_kind=td.decision_kind,
        decided_at=td.decided_at,
        notes=td.notes,
        kyc_gate=gate_obj,
        kyc_state=kyc_state,
        kyc_requires_override=kyc_requires_override,
        created_by_user_id=td.created_by_user_id,
        created_at=td.created_at,
        kyc_override=override_obj,
    )


@router.get(
    "",
    response_model=TreasuryDecisionListRead,
    dependencies=[Depends(require_roles(models.RoleName.financeiro, models.RoleName.auditoria))],
)
def list_decisions(
    exposure_id: int | None = Query(None),
    db: Session = _DB_DEP,
):
    items = list_treasury_decisions(db=db, exposure_id=exposure_id)
    return TreasuryDecisionListRead(items=[_to_read_model(td) for td in items])


@router.get(
    "/{decision_id}",
    response_model=TreasuryDecisionRead,
    dependencies=[Depends(require_roles(models.RoleName.financeiro, models.RoleName.auditoria))],
)
def get_decision(
    decision_id: int,
    db: Session = _DB_DEP,
):
    td = get_treasury_decision(db=db, decision_id=decision_id)
    if not td:
        raise HTTPException(status_code=404, detail="TreasuryDecision not found")
    return _to_read_model(td)


@router.post(
    "",
    response_model=TreasuryDecisionRead,
    dependencies=[Depends(require_roles(models.RoleName.financeiro))],
)
def create_decision(
    payload: TreasuryDecisionCreate,
    request: Request,
    db: Session = _DB_DEP,
    user: models.User = Depends(require_roles(models.RoleName.financeiro)),
):
    try:
        td = create_treasury_decision(
            db=db,
            exposure_id=payload.exposure_id,
            decision_kind=payload.decision_kind,
            notes=payload.notes,
            decided_at=payload.decided_at,
            actor_user_id=getattr(user, "id", None),
            request_id=str(request.headers.get("X-Request-ID") or "") or None,
            ip=str(getattr(request.client, "host", None) or "") or None,
            user_agent=str(request.headers.get("User-Agent") or "") or None,
        )
    except ValueError as e:
        if str(e) == "exposure_not_found":
            raise HTTPException(status_code=404, detail="Exposure not found")
        raise

    return _to_read_model(td)


@router.post(
    "/{decision_id}/kyc-overrides",
    response_model=TreasuryDecisionRead,
    dependencies=[Depends(require_roles(models.RoleName.admin))],
)
def create_decision_kyc_override(
    decision_id: int,
    payload: TreasuryKycOverrideCreate,
    request: Request,
    db: Session = _DB_DEP,
    user: models.User = Depends(require_roles(models.RoleName.admin)),
):
    td = get_treasury_decision(db=db, decision_id=decision_id)
    if not td:
        raise HTTPException(status_code=404, detail="TreasuryDecision not found")

    create_kyc_override(
        db=db,
        decision=td,
        reason=payload.reason,
        actor_user_id=getattr(user, "id", None),
        request_id=str(request.headers.get("X-Request-ID") or "") or None,
        ip=str(getattr(request.client, "host", None) or "") or None,
        user_agent=str(request.headers.get("User-Agent") or "") or None,
    )

    # Reload to include relationship.
    db.refresh(td)
    return _to_read_model(td)
