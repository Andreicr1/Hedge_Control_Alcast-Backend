from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.exports_manifest import compute_export_id_and_hash
from app.services.finance_pipeline_daily import execute_finance_pipeline_daily

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _noop(_db, _plan, _run):
    return None


def test_exports_step_is_skipped_when_emit_exports_false():
    step_impls = {
        "market_snapshot_resolve": _noop,
        "mtm_snapshot": _noop,
        "pnl_snapshot": _noop,
        "cashflow_baseline": _noop,
        "risk_flags": _noop,
    }

    with TestingSessionLocal() as db:
        res = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 123},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000e001",
            step_impls=step_impls,
        )
        db.commit()

        assert db.query(models.ExportJob).count() == 0

        step = (
            db.query(models.FinancePipelineStep)
            .filter(models.FinancePipelineStep.run_id == int(res.run_id))
            .filter(models.FinancePipelineStep.step_name == "exports")
            .first()
        )
        assert step is not None
        assert step.status == "skipped"


def test_exports_job_created_deterministically_when_emit_exports_true_and_idempotent():
    step_impls = {
        "market_snapshot_resolve": _noop,
        "mtm_snapshot": _noop,
        "pnl_snapshot": _noop,
        "cashflow_baseline": _noop,
        "risk_flags": _noop,
    }

    with TestingSessionLocal() as db:
        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 123},
            mode="materialize",
            emit_exports=True,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000e002",
            step_impls=step_impls,
        )
        db.commit()

        assert db.query(models.ExportJob).count() == 1

        job = db.query(models.ExportJob).first()
        assert job is not None
        assert job.export_type == "state_at_time"

        expected_export_id, expected_inputs_hash = compute_export_id_and_hash(
            export_type="state_at_time",
            as_of=datetime(2026, 1, 16, tzinfo=timezone.utc),
            filters={"deal_id": 123},
        )
        assert job.export_id == expected_export_id
        assert job.inputs_hash == expected_inputs_hash

        step = (
            db.query(models.FinancePipelineStep)
            .filter(models.FinancePipelineStep.run_id == int(r1.run_id))
            .filter(models.FinancePipelineStep.step_name == "exports")
            .first()
        )
        assert step is not None
        assert step.status == "done"
        assert step.artifacts is not None
        assert step.artifacts["export_ids"] == [expected_export_id]

        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 123},
            mode="materialize",
            emit_exports=True,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000e003",
            step_impls=step_impls,
        )
        db.commit()

        assert r2.inputs_hash == r1.inputs_hash
        assert db.query(models.ExportJob).count() == 1


def test_dry_run_does_not_create_export_job_even_when_emit_exports_true():
    with TestingSessionLocal() as db:
        res = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 123},
            mode="dry_run",
            emit_exports=True,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000e004",
            step_impls=None,
        )
        assert res.plan.emit_exports is True
        assert db.query(models.ExportJob).count() == 0
