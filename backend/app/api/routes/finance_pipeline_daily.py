from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import models
from app.api.deps import require_roles
from app.database import get_db
from app.schemas.finance_pipeline import (
    FinancePipelineDailyDryRunResponse,
    FinancePipelineDailyRunRequest,
    FinancePipelineDailyRunResponse,
    FinancePipelineDailyRunStatusResponse,
    FinancePipelineStepStatus,
)
from app.services.finance_pipeline_daily import ORDERED_STEPS, execute_finance_pipeline_daily

router = APIRouter(prefix="/pipelines/finance/daily", tags=["pipelines"])


_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


_db_dep = Depends(get_db)
_finance_or_admin_user_dep = Depends(
    require_roles(models.RoleName.financeiro, models.RoleName.admin)
)
_finance_admin_or_audit_user_dep = Depends(
    require_roles(models.RoleName.financeiro, models.RoleName.admin, models.RoleName.auditoria)
)


def _step_rows_for_run(run: models.FinancePipelineRun) -> list[FinancePipelineStepStatus]:
    existing = {str(s.step_name): s for s in list(run.steps or [])}
    out: list[FinancePipelineStepStatus] = []
    for step_name in ORDERED_STEPS:
        name = str(step_name)
        if name in existing:
            out.append(
                FinancePipelineStepStatus(
                    step_name=name,
                    status=str(existing[name].status),
                )
            )
        else:
            out.append(FinancePipelineStepStatus(step_name=name, status="pending"))
    return out


def _status_response_for_run(
    run: models.FinancePipelineRun,
) -> FinancePipelineDailyRunStatusResponse:
    return FinancePipelineDailyRunStatusResponse(
        run_id=int(run.id),
        mode="materialize",
        inputs_hash=str(run.inputs_hash),
        status=str(run.status),
        as_of_date=run.as_of_date,
        pipeline_version=str(run.pipeline_version),
        scope_filters=dict(run.scope_filters or {}),
        emit_exports=bool(run.emit_exports),
        requested_by_user_id=getattr(run, "requested_by_user_id", None),
        started_at=getattr(run, "started_at", None),
        completed_at=getattr(run, "completed_at", None),
        error_code=getattr(run, "error_code", None),
        error_message=getattr(run, "error_message", None),
        steps=_step_rows_for_run(run),
    )


@router.post(
    "/run",
    response_model=FinancePipelineDailyRunResponse,
    status_code=status.HTTP_200_OK,
)
def run_finance_pipeline_daily(
    request: Request,
    payload: FinancePipelineDailyRunRequest,
    db: Session = _db_dep,
    current_user: models.User = _finance_or_admin_user_dep,
):
    # Correlation: propagate X-Request-ID to service (same semantics as Timeline emitters).
    request_id = request.headers.get("X-Request-ID")

    res = execute_finance_pipeline_daily(
        db,
        as_of_date=payload.as_of_date,
        pipeline_version=payload.pipeline_version,
        scope_filters=payload.scope_filters,
        mode=payload.mode,
        emit_exports=payload.emit_exports,
        requested_by_user_id=getattr(current_user, "id", None),
        request_id=request_id,
        step_impls=None,
    )

    if payload.mode == "dry_run":
        return FinancePipelineDailyDryRunResponse(
            mode="dry_run",
            inputs_hash=res.plan.inputs_hash,
            as_of_date=res.plan.as_of_date,
            pipeline_version=res.plan.pipeline_version,
            scope_filters=dict(res.plan.scope_filters or {}),
            emit_exports=bool(res.plan.emit_exports),
            ordered_steps=list(res.ordered_steps),
        )

    run = (
        db.query(models.FinancePipelineRun)
        .filter(models.FinancePipelineRun.id == int(res.run_id))
        .first()
    )
    if run is None:
        raise HTTPException(status_code=500, detail="Pipeline run not found after execution")

    return _status_response_for_run(run)


@router.get(
    "/runs/{run_ref}",
    response_model=FinancePipelineDailyRunStatusResponse,
    status_code=status.HTTP_200_OK,
)
def get_finance_pipeline_daily_run(
    run_ref: str,
    db: Session = _db_dep,
    _current_user: models.User = _finance_admin_or_audit_user_dep,
):
    run: models.FinancePipelineRun | None = None

    if run_ref.isdigit():
        run = (
            db.query(models.FinancePipelineRun)
            .filter(models.FinancePipelineRun.id == int(run_ref))
            .first()
        )
    else:
        key = str(run_ref).strip().lower()
        if not _HEX_64_RE.match(key):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "finance.pipeline.run_ref.invalid",
                    "run_ref": run_ref,
                },
            )
        run = (
            db.query(models.FinancePipelineRun)
            .filter(models.FinancePipelineRun.inputs_hash == key)
            .first()
        )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "finance.pipeline.run.not_found",
                "run_ref": run_ref,
            },
        )

    return _status_response_for_run(run)
