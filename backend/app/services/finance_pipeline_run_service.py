from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

FinancePipelineMode = Literal["materialize", "dry_run"]

_FINANCE_PIPELINE_RUN_SCHEMA_VERSION = "finance.pipeline.daily.run.v1"


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _jsonable(vv) for k, vv in sorted(v.items(), key=lambda x: str(x[0]))}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return str(v)


def normalize_scope_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    f = dict(filters or {})
    out: dict[str, Any] = {}
    for k, v in f.items():
        if v is None:
            continue
        out[str(k)] = v
    return out


def compute_finance_pipeline_inputs_hash(
    *,
    as_of_date: date,
    pipeline_version: str,
    scope_filters: dict[str, Any] | None,
    mode: FinancePipelineMode,
    emit_exports: bool,
) -> str:
    payload = {
        "schema_version": _FINANCE_PIPELINE_RUN_SCHEMA_VERSION,
        "pipeline_version": str(pipeline_version),
        "as_of_date": as_of_date.isoformat(),
        "scope_filters": _jsonable(normalize_scope_filters(scope_filters)),
        "mode": str(mode),
        "emit_exports": bool(emit_exports),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class FinancePipelineRunPlan:
    as_of_date: date
    pipeline_version: str
    scope_filters: dict[str, Any]
    mode: FinancePipelineMode
    emit_exports: bool
    inputs_hash: str


def build_finance_pipeline_run_plan(
    *,
    as_of_date: date,
    pipeline_version: str,
    scope_filters: dict[str, Any] | None,
    mode: FinancePipelineMode,
    emit_exports: bool,
) -> FinancePipelineRunPlan:
    nf = normalize_scope_filters(scope_filters)
    inputs_hash = compute_finance_pipeline_inputs_hash(
        as_of_date=as_of_date,
        pipeline_version=pipeline_version,
        scope_filters=nf,
        mode=mode,
        emit_exports=emit_exports,
    )
    return FinancePipelineRunPlan(
        as_of_date=as_of_date,
        pipeline_version=str(pipeline_version),
        scope_filters=nf,
        mode=mode,
        emit_exports=emit_exports,
        inputs_hash=inputs_hash,
    )


def ensure_finance_pipeline_run(
    db: Session,
    *,
    as_of_date: date,
    pipeline_version: str,
    scope_filters: dict[str, Any] | None,
    mode: FinancePipelineMode,
    emit_exports: bool,
    requested_by_user_id: int | None,
) -> models.FinancePipelineRun:
    plan = build_finance_pipeline_run_plan(
        as_of_date=as_of_date,
        pipeline_version=pipeline_version,
        scope_filters=scope_filters,
        mode=mode,
        emit_exports=emit_exports,
    )

    existing = (
        db.query(models.FinancePipelineRun)
        .filter(models.FinancePipelineRun.inputs_hash == plan.inputs_hash)
        .first()
    )
    if existing is not None:
        return existing

    run = models.FinancePipelineRun(
        pipeline_version=plan.pipeline_version,
        as_of_date=plan.as_of_date,
        scope_filters=plan.scope_filters,
        mode=plan.mode,
        emit_exports=bool(plan.emit_exports),
        inputs_hash=plan.inputs_hash,
        requested_by_user_id=requested_by_user_id,
        status="queued",
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.FinancePipelineRun)
            .filter(models.FinancePipelineRun.inputs_hash == plan.inputs_hash)
            .first()
        )
        if existing is None:
            raise
        return existing

    return run


_RUN_STATUS_ORDER = {
    "queued": 0,
    "running": 1,
    "done": 2,
    "failed": 2,
}


_STEP_STATUS_ORDER = {
    "pending": 0,
    "running": 1,
    "done": 2,
    "failed": 2,
    "skipped": 2,
}


def ensure_finance_pipeline_step(
    db: Session,
    *,
    run_id: int,
    step_name: str,
) -> models.FinancePipelineStep:
    existing = (
        db.query(models.FinancePipelineStep)
        .filter(models.FinancePipelineStep.run_id == int(run_id))
        .filter(models.FinancePipelineStep.step_name == str(step_name))
        .first()
    )
    if existing is not None:
        return existing

    step = models.FinancePipelineStep(
        run_id=int(run_id),
        step_name=str(step_name),
        status="pending",
    )
    db.add(step)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(models.FinancePipelineStep)
            .filter(models.FinancePipelineStep.run_id == int(run_id))
            .filter(models.FinancePipelineStep.step_name == str(step_name))
            .first()
        )
        if existing is None:
            raise
        return existing

    return step


def transition_finance_pipeline_step_status(
    db: Session,
    *,
    step: models.FinancePipelineStep,
    new_status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    allow_resume_from_failed: bool = False,
) -> models.FinancePipelineStep:
    if new_status not in _STEP_STATUS_ORDER:
        raise ValueError(f"Invalid finance pipeline step status: {new_status}")

    old = str(getattr(step, "status", "pending") or "pending")
    if old not in _STEP_STATUS_ORDER:
        old = "pending"

    if allow_resume_from_failed and old == "failed" and new_status == "running":
        step.status = "running"
        if step.started_at is None:
            step.started_at = datetime.now(timezone.utc)
        db.flush()
        return step

    if _STEP_STATUS_ORDER[new_status] < _STEP_STATUS_ORDER[old]:
        raise ValueError(f"Invalid step transition: {old} -> {new_status}")
    if old in {"done", "skipped"} and new_status != old:
        raise ValueError(f"Step is terminal; cannot transition: {old} -> {new_status}")

    step.status = new_status

    if new_status == "running" and step.started_at is None:
        step.started_at = datetime.now(timezone.utc)

    if new_status in {"done", "failed", "skipped"}:
        if step.completed_at is None:
            step.completed_at = datetime.now(timezone.utc)
        if new_status == "failed":
            step.error_code = error_code
            step.error_message = error_message

    db.flush()
    return step


def transition_finance_pipeline_run_status(
    db: Session,
    *,
    run: models.FinancePipelineRun,
    new_status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    allow_resume_from_failed: bool = False,
) -> models.FinancePipelineRun:
    if new_status not in _RUN_STATUS_ORDER:
        raise ValueError(f"Invalid finance pipeline run status: {new_status}")

    old = str(getattr(run, "status", "queued") or "queued")
    if old not in _RUN_STATUS_ORDER:
        old = "queued"

    if allow_resume_from_failed and old == "failed" and new_status == "running":
        run.status = "running"
        if run.started_at is None:
            run.started_at = datetime.now(timezone.utc)
        db.flush()
        return run

    if _RUN_STATUS_ORDER[new_status] < _RUN_STATUS_ORDER[old]:
        raise ValueError(f"Invalid transition: {old} -> {new_status}")
    if old == "done" and new_status != old:
        raise ValueError(f"Run is terminal; cannot transition: {old} -> {new_status}")

    run.status = new_status

    if new_status == "running" and run.started_at is None:
        run.started_at = datetime.now(timezone.utc)

    if new_status in {"done", "failed"}:
        if run.completed_at is None:
            run.completed_at = datetime.now(timezone.utc)
        if new_status == "failed":
            run.error_code = error_code
            run.error_message = error_message

    db.flush()
    return run
