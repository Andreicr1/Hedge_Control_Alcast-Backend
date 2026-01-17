from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Literal

from sqlalchemy.orm import Session

from app import models
from app.services.cashflow_baseline_service import (
    CashflowBaselineMaterializeResult,
    execute_cashflow_baseline_run,
)
from app.services.exports_job_service import ensure_export_job
from app.services.finance_pipeline_run_service import (
    FinancePipelineMode,
    FinancePipelineRunPlan,
    build_finance_pipeline_run_plan,
    ensure_finance_pipeline_run,
    ensure_finance_pipeline_step,
    transition_finance_pipeline_run_status,
    transition_finance_pipeline_step_status,
)
from app.services.finance_pipeline_timeline import emit_finance_pipeline_timeline_event
from app.services.finance_risk_flags_service import (
    FinanceRiskFlagsMaterializeResult,
    execute_finance_risk_flags_run,
)
from app.services.mtm_contract_snapshot_service import (
    MtmContractSnapshotMaterializeResult,
    execute_mtm_contract_snapshot_run,
)
from app.services.mtm_contract_timeline import emit_mtm_contract_snapshot_created
from app.services.pnl_snapshot_service import PnlSnapshotMaterializeResult, execute_pnl_snapshot_run
from app.services.pnl_timeline import emit_pnl_snapshot_created
from app.services.timeline_emitters import correlation_id_from_request_id

FinancePipelineStepName = Literal[
    "market_snapshot_resolve",
    "mtm_snapshot",
    "pnl_snapshot",
    "cashflow_baseline",
    "risk_flags",
    "exports",
]


ORDERED_STEPS: list[FinancePipelineStepName] = [
    "market_snapshot_resolve",
    "mtm_snapshot",
    "pnl_snapshot",
    "cashflow_baseline",
    "risk_flags",
    "exports",
]


@dataclass(frozen=True)
class FinancePipelineDailyDryRunResult:
    plan: FinancePipelineRunPlan
    ordered_steps: list[str]


@dataclass(frozen=True)
class FinancePipelineDailyMaterializeResult:
    run_id: int
    inputs_hash: str
    status: str
    steps: list[dict[str, Any]]


StepArtifacts = dict[str, Any]
StepImpl = Callable[
    [Session, FinancePipelineRunPlan, models.FinancePipelineRun],
    StepArtifacts | None,
]


def _default_mtm_snapshot_step(
    db: Session,
    plan: FinancePipelineRunPlan,
    run: models.FinancePipelineRun,
    *,
    request_id: str | None,
    actor_user_id: int | None,
) -> StepArtifacts:
    res = execute_mtm_contract_snapshot_run(
        db,
        as_of_date=plan.as_of_date,
        filters=dict(plan.scope_filters or {}),
        requested_by_user_id=actor_user_id,
        dry_run=False,
    )
    if not isinstance(res, MtmContractSnapshotMaterializeResult):
        raise RuntimeError("Unexpected MTM contract snapshot result type")

    # Post-commit timeline: MTM writes must be persisted before emitting.
    db.commit()

    correlation_id = correlation_id_from_request_id(request_id)
    emit_mtm_contract_snapshot_created(
        db=db,
        run_id=int(res.run_id),
        inputs_hash=str(res.inputs_hash),
        as_of_date=plan.as_of_date,
        filters=dict(plan.scope_filters or {}),
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
        meta={
            "written": int(res.written),
            "skipped_existing": int(res.skipped_existing),
            "skipped_not_computable": int(res.skipped_not_computable),
            "snapshots": int(len(res.snapshot_ids)),
        },
    )

    return {
        "mtm_contract_snapshot_run_id": int(res.run_id),
        "mtm_inputs_hash": str(res.inputs_hash),
        "mtm_contract_snapshot_ids": list(res.snapshot_ids),
        "written": int(res.written),
        "skipped_existing": int(res.skipped_existing),
        "skipped_not_computable": int(res.skipped_not_computable),
    }


def _default_pnl_snapshot_step(
    db: Session,
    plan: FinancePipelineRunPlan,
    run: models.FinancePipelineRun,
    *,
    request_id: str | None,
    actor_user_id: int | None,
) -> StepArtifacts:
    res = execute_pnl_snapshot_run(
        db,
        as_of_date=plan.as_of_date,
        filters=dict(plan.scope_filters or {}),
        requested_by_user_id=actor_user_id,
        dry_run=False,
    )
    if not isinstance(res, PnlSnapshotMaterializeResult):
        raise RuntimeError("Unexpected P&L snapshot result type")

    # Post-commit timeline: P&L writes must be persisted before emitting.
    db.commit()

    correlation_id = correlation_id_from_request_id(request_id)
    emit_pnl_snapshot_created(
        db=db,
        run_id=int(res.run_id),
        inputs_hash=str(res.inputs_hash),
        as_of_date=plan.as_of_date,
        filters=dict(plan.scope_filters or {}),
        correlation_id=correlation_id,
        actor_user_id=actor_user_id,
        meta={
            "unrealized_written": int(res.unrealized_written),
            "realized_locked_written": int(res.realized_locked_written),
        },
    )

    return {
        "pnl_snapshot_run_id": int(res.run_id),
        "pnl_inputs_hash": str(res.inputs_hash),
        "unrealized_written": int(res.unrealized_written),
        "unrealized_updated": int(res.unrealized_updated),
        "realized_locked_written": int(res.realized_locked_written),
    }


def _default_cashflow_baseline_step(
    db: Session,
    plan: FinancePipelineRunPlan,
    run: models.FinancePipelineRun,
    *,
    actor_user_id: int | None,
) -> StepArtifacts:
    res = execute_cashflow_baseline_run(
        db,
        as_of_date=plan.as_of_date,
        filters=dict(plan.scope_filters or {}),
        requested_by_user_id=actor_user_id,
        dry_run=False,
    )
    if not isinstance(res, CashflowBaselineMaterializeResult):
        raise RuntimeError("Unexpected cashflow baseline result type")

    return {
        "cashflow_baseline_run_id": int(res.run_id),
        "cashflow_baseline_inputs_hash": str(res.inputs_hash),
        "cashflow_baseline_item_ids": list(res.item_ids),
        "written": int(res.written),
        "skipped_existing": int(res.skipped_existing),
        "mtm_missing": int(res.mtm_missing),
        "pnl_missing": int(res.pnl_missing),
        "missing_settlement_date": int(res.missing_settlement_date),
    }


def _default_risk_flags_step(
    db: Session,
    plan: FinancePipelineRunPlan,
    run: models.FinancePipelineRun,
    *,
    actor_user_id: int | None,
) -> StepArtifacts:
    res = execute_finance_risk_flags_run(
        db,
        as_of_date=plan.as_of_date,
        filters=dict(plan.scope_filters or {}),
        requested_by_user_id=actor_user_id,
        dry_run=False,
    )
    if not isinstance(res, FinanceRiskFlagsMaterializeResult):
        raise RuntimeError("Unexpected finance risk flags result type")

    return {
        "finance_risk_flags_run_id": int(res.run_id),
        "finance_risk_flags_inputs_hash": str(res.inputs_hash),
        "finance_risk_flag_ids": list(res.flag_ids),
        "written": int(res.written),
        "skipped_existing": int(res.skipped_existing),
    }


def _default_exports_step(
    db: Session,
    plan: FinancePipelineRunPlan,
    run: models.FinancePipelineRun,
    *,
    actor_user_id: int | None,
) -> StepArtifacts:
    # Deterministic cutoff: midnight UTC on as_of_date.
    as_of_dt = datetime(
        plan.as_of_date.year,
        plan.as_of_date.month,
        plan.as_of_date.day,
        tzinfo=timezone.utc,
    )

    job, idempotent = ensure_export_job(
        db,
        export_type="state_at_time",
        as_of=as_of_dt,
        filters=dict(plan.scope_filters or {}),
        requested_by_user_id=actor_user_id,
    )

    return {
        "export_jobs": [
            {
                "export_id": str(job.export_id),
                "export_job_db_id": int(job.id),
                "inputs_hash": str(job.inputs_hash),
                "export_type": str(job.export_type),
                "status": str(job.status),
                "idempotent": bool(idempotent),
            }
        ],
        "export_ids": [str(job.export_id)],
        "export_job_count": 1,
    }


def dry_run_finance_pipeline_daily(
    *,
    as_of_date: date,
    pipeline_version: str,
    scope_filters: dict[str, Any] | None,
    emit_exports: bool,
) -> FinancePipelineDailyDryRunResult:
    plan = build_finance_pipeline_run_plan(
        as_of_date=as_of_date,
        pipeline_version=pipeline_version,
        scope_filters=scope_filters,
        mode="dry_run",
        emit_exports=emit_exports,
    )
    return FinancePipelineDailyDryRunResult(plan=plan, ordered_steps=list(ORDERED_STEPS))


def execute_finance_pipeline_daily(
    db: Session,
    *,
    as_of_date: date,
    pipeline_version: str,
    scope_filters: dict[str, Any] | None,
    mode: FinancePipelineMode,
    emit_exports: bool,
    requested_by_user_id: int | None,
    request_id: str | None = None,
    step_impls: dict[str, StepImpl] | None = None,
) -> FinancePipelineDailyDryRunResult | FinancePipelineDailyMaterializeResult:
    if mode == "dry_run":
        return dry_run_finance_pipeline_daily(
            as_of_date=as_of_date,
            pipeline_version=pipeline_version,
            scope_filters=scope_filters,
            emit_exports=emit_exports,
        )

    plan = build_finance_pipeline_run_plan(
        as_of_date=as_of_date,
        pipeline_version=pipeline_version,
        scope_filters=scope_filters,
        mode=mode,
        emit_exports=emit_exports,
    )

    run = ensure_finance_pipeline_run(
        db,
        as_of_date=plan.as_of_date,
        pipeline_version=plan.pipeline_version,
        scope_filters=plan.scope_filters,
        mode=plan.mode,
        emit_exports=plan.emit_exports,
        requested_by_user_id=requested_by_user_id,
    )

    if run.status == "done":
        existing_steps = {s.step_name: s for s in list(run.steps or [])}
        step_rows: list[dict[str, Any]] = []
        for step_name in ORDERED_STEPS:
            name = str(step_name)
            if name in existing_steps:
                status = str(existing_steps[name].status)
            else:
                status = "pending"
            step_rows.append({"step_name": name, "status": status})
        return FinancePipelineDailyMaterializeResult(
            run_id=int(run.id),
            inputs_hash=str(run.inputs_hash),
            status=str(run.status),
            steps=step_rows,
        )

    # Post-commit rule: ensure the run row exists before emitting REQUESTED.
    db.commit()
    db.refresh(run)
    emit_finance_pipeline_timeline_event(
        db,
        event="requested",
        run=run,
        request_id=request_id,
        actor_user_id=requested_by_user_id,
    )

    if run.status == "failed":
        transition_finance_pipeline_run_status(
            db,
            run=run,
            new_status="running",
            allow_resume_from_failed=True,
        )
    else:
        transition_finance_pipeline_run_status(db, run=run, new_status="running")

    # Post-commit rule: emit STARTED only after the transition is persisted.
    db.commit()
    db.refresh(run)
    emit_finance_pipeline_timeline_event(
        db,
        event="started",
        run=run,
        request_id=request_id,
        actor_user_id=requested_by_user_id,
    )

    impls = dict(step_impls or {})

    step_rows: list[dict[str, Any]] = []

    for step_name in ORDERED_STEPS:
        step = ensure_finance_pipeline_step(db, run_id=int(run.id), step_name=str(step_name))

        if step.status in {"done", "skipped"}:
            step_rows.append({"step_name": step.step_name, "status": step.status})
            continue

        # Exports hook is optional. When emit_exports is false, mark the step as skipped.
        if str(step_name) == "exports" and not bool(plan.emit_exports):
            transition_finance_pipeline_step_status(db, step=step, new_status="skipped")
            step_rows.append({"step_name": step.step_name, "status": step.status})
            continue

        if step.status == "failed":
            transition_finance_pipeline_step_status(
                db,
                step=step,
                new_status="running",
                allow_resume_from_failed=True,
            )
        else:
            transition_finance_pipeline_step_status(db, step=step, new_status="running")

        impl = impls.get(str(step_name))
        if impl is None and str(step_name) == "mtm_snapshot":

            def _impl(
                _db: Session,
                _plan: FinancePipelineRunPlan,
                _run: models.FinancePipelineRun,
            ):
                return _default_mtm_snapshot_step(
                    _db,
                    _plan,
                    _run,
                    request_id=request_id,
                    actor_user_id=requested_by_user_id,
                )

            impl = _impl
        if impl is None and str(step_name) == "pnl_snapshot":

            def _impl(
                _db: Session,
                _plan: FinancePipelineRunPlan,
                _run: models.FinancePipelineRun,
            ):
                return _default_pnl_snapshot_step(
                    _db,
                    _plan,
                    _run,
                    request_id=request_id,
                    actor_user_id=requested_by_user_id,
                )

            impl = _impl
        if impl is None and str(step_name) == "cashflow_baseline":

            def _impl(
                _db: Session,
                _plan: FinancePipelineRunPlan,
                _run: models.FinancePipelineRun,
            ):
                return _default_cashflow_baseline_step(
                    _db,
                    _plan,
                    _run,
                    actor_user_id=requested_by_user_id,
                )

            impl = _impl
        if impl is None and str(step_name) == "risk_flags":

            def _impl(
                _db: Session,
                _plan: FinancePipelineRunPlan,
                _run: models.FinancePipelineRun,
            ):
                return _default_risk_flags_step(
                    _db,
                    _plan,
                    _run,
                    actor_user_id=requested_by_user_id,
                )

            impl = _impl

        if impl is None and str(step_name) == "exports":

            def _impl(
                _db: Session,
                _plan: FinancePipelineRunPlan,
                _run: models.FinancePipelineRun,
            ):
                return _default_exports_step(
                    _db,
                    _plan,
                    _run,
                    actor_user_id=requested_by_user_id,
                )

            impl = _impl
        if impl is None:
            transition_finance_pipeline_step_status(
                db,
                step=step,
                new_status="failed",
                error_code="step_not_implemented",
                error_message=f"No implementation registered for step '{step_name}'",
            )
            transition_finance_pipeline_run_status(
                db,
                run=run,
                new_status="failed",
                error_code="step_not_implemented",
                error_message=f"No implementation registered for step '{step_name}'",
            )

            # Post-commit rule: emit FAILED only after the transition is persisted.
            db.commit()
            db.refresh(run)
            emit_finance_pipeline_timeline_event(
                db,
                event="failed",
                run=run,
                request_id=request_id,
                actor_user_id=requested_by_user_id,
                extra_payload={
                    "error_code": str(run.error_code) if run.error_code else None,
                    "error_message": str(run.error_message) if run.error_message else None,
                },
            )
            break

        try:
            artifacts = impl(db, plan, run)
        except Exception as exc:  # noqa: BLE001
            transition_finance_pipeline_step_status(
                db,
                step=step,
                new_status="failed",
                error_code=type(exc).__name__,
                error_message=str(exc)[:2000],
            )
            transition_finance_pipeline_run_status(
                db,
                run=run,
                new_status="failed",
                error_code=type(exc).__name__,
                error_message=str(exc)[:2000],
            )

            # Post-commit rule: emit FAILED only after the transition is persisted.
            db.commit()
            db.refresh(run)
            emit_finance_pipeline_timeline_event(
                db,
                event="failed",
                run=run,
                request_id=request_id,
                actor_user_id=requested_by_user_id,
                extra_payload={
                    "error_code": str(run.error_code) if run.error_code else None,
                    "error_message": str(run.error_message) if run.error_message else None,
                },
            )
            break

        if artifacts:
            step.artifacts = dict(artifacts)
            db.flush()

        transition_finance_pipeline_step_status(db, step=step, new_status="done")
        step_rows.append({"step_name": step.step_name, "status": step.status})

    if run.status == "running":
        transition_finance_pipeline_run_status(db, run=run, new_status="done")

        # Post-commit rule: emit COMPLETED only after the transition is persisted.
        db.commit()
        db.refresh(run)
        emit_finance_pipeline_timeline_event(
            db,
            event="completed",
            run=run,
            request_id=request_id,
            actor_user_id=requested_by_user_id,
        )

    return FinancePipelineDailyMaterializeResult(
        run_id=int(run.id),
        inputs_hash=str(run.inputs_hash),
        status=str(run.status),
        steps=step_rows,
    )
