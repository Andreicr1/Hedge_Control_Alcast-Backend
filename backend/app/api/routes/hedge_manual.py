# ruff: noqa: B008

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas import HedgeCreateManual, HedgeReadManual
from app.services.timeline_emitters import correlation_id_from_request_id
from app.services.workflow_approvals import mark_workflow_executed, require_approval_or_raise

router = APIRouter(prefix="/hedges/manual", tags=["hedges_manual"])


@router.post("", response_model=HedgeReadManual, status_code=status.HTTP_201_CREATED)
def create_manual_hedge(
    request: Request,
    payload: HedgeCreateManual,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.RoleName.admin, models.RoleName.financeiro)
    ),
):
    counterparty = db.get(models.Counterparty, payload.counterparty_id)
    if not counterparty:
        raise HTTPException(status_code=400, detail="Counterparty not found")

    if not payload.exposures:
        raise HTTPException(status_code=400, detail="At least one exposure is required")

    # Preflight validate exposures read-only (avoid approvals for obviously invalid requests).
    for link in payload.exposures:
        exposure = db.get(models.Exposure, link.exposure_id)
        if not exposure:
            raise HTTPException(status_code=404, detail=f"Exposure {link.exposure_id} not found")
        if exposure.status == models.ExposureStatus.closed:
            raise HTTPException(status_code=400, detail=f"Exposure {link.exposure_id} closed")

    correlation_id = correlation_id_from_request_id(request.headers.get("X-Request-ID"))

    notional_usd: float | None = None
    try:
        notional_usd = float(payload.quantity_mt) * float(payload.contract_price)
    except Exception:
        notional_usd = None

    wf = require_approval_or_raise(
        db=db,
        action="hedge.manual.create",
        subject_type="hedge_manual",
        subject_id=str(payload.reference_code or "new"),
        notional_usd=notional_usd,
        context={
            "counterparty_id": payload.counterparty_id,
            "quantity_mt": payload.quantity_mt,
            "contract_price": payload.contract_price,
            "period": payload.period,
            "instrument": payload.instrument,
            "maturity_date": payload.maturity_date.isoformat() if payload.maturity_date else None,
            "reference_code": payload.reference_code,
            "exposures": [
                {"exposure_id": e.exposure_id, "quantity_mt": e.quantity_mt}
                for e in (payload.exposures or [])
            ],
        },
        requested_by_user_id=getattr(current_user, "id", None),
        correlation_id=correlation_id,
        workflow_request_id=getattr(payload, "workflow_request_id", None),
        request_id=request.headers.get("X-Request-ID"),
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("User-Agent"),
    )

    hedge = models.Hedge(
        counterparty_id=payload.counterparty_id,
        quantity_mt=payload.quantity_mt,
        contract_price=payload.contract_price,
        period=payload.period,
        instrument=payload.instrument,
        maturity_date=payload.maturity_date,
        reference_code=payload.reference_code,
        status=models.HedgeStatus.active,
    )
    db.add(hedge)
    db.flush()

    for link in payload.exposures:
        exposure = db.get(models.Exposure, link.exposure_id)
        db.add(
            models.HedgeExposure(
                hedge_id=hedge.id,
                exposure_id=exposure.id,
                quantity_mt=link.quantity_mt,
            )
        )
        # update exposure status
        remaining = exposure.quantity_mt - link.quantity_mt
        if remaining <= 0:
            exposure.status = models.ExposureStatus.hedged
        else:
            exposure.status = models.ExposureStatus.partially_hedged
        for task in exposure.tasks:
            task.status = models.HedgeTaskStatus.hedged
        db.add(exposure)

    db.commit()
    db.refresh(hedge)

    if wf is not None:
        mark_workflow_executed(
            db=db,
            workflow_request_id=int(wf.id),
            executed_by_user_id=getattr(current_user, "id", None),
            request_id=request.headers.get("X-Request-ID"),
            ip=(request.client.host if request.client else None),
            user_agent=request.headers.get("User-Agent"),
        )
    return hedge
