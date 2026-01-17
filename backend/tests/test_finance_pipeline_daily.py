from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.finance_pipeline_daily import ORDERED_STEPS, execute_finance_pipeline_daily

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


def test_pipeline_dry_run_does_not_write_any_tables():
    with TestingSessionLocal() as db:
        res = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 10},
            mode="dry_run",
            emit_exports=True,
            requested_by_user_id=1,
        )

        assert res.plan.inputs_hash
        assert len(res.ordered_steps) == len(ORDERED_STEPS)

        assert db.query(models.FinancePipelineRun).count() == 0
        assert db.query(models.FinancePipelineStep).count() == 0


def test_pipeline_materialize_is_idempotent_creating_one_run_and_steps():
    with TestingSessionLocal() as db:
        called: list[str] = []

        def _mk(step_name: str):
            def _impl(_db, _plan, _run):
                called.append(step_name)

            return _impl

        impls = {str(s): _mk(str(s)) for s in ORDERED_STEPS}

        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            step_impls=impls,
        )
        db.commit()

        assert r1.status == "done"
        assert db.query(models.FinancePipelineRun).count() == 1
        assert db.query(models.FinancePipelineStep).count() == len(ORDERED_STEPS)

        called.clear()

        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            step_impls=impls,
        )
        db.commit()

        assert r2.inputs_hash == r1.inputs_hash
        assert db.query(models.FinancePipelineRun).count() == 1
        assert db.query(models.FinancePipelineStep).count() == len(ORDERED_STEPS)
        assert called == []


def test_pipeline_failed_step_marks_run_failed_and_can_resume():
    with TestingSessionLocal() as db:
        calls: dict[str, int] = {str(s): 0 for s in ORDERED_STEPS}

        def ok(step_name: str):
            def _impl(_db, _plan, _run):
                calls[step_name] += 1

            return _impl

        def boom(_db, _plan, _run):
            calls["pnl_snapshot"] += 1
            raise RuntimeError("kaboom")

        impls_fail = {str(s): ok(str(s)) for s in ORDERED_STEPS}
        impls_fail["pnl_snapshot"] = boom

        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            step_impls=impls_fail,
        )
        db.commit()

        assert r1.status == "failed"

        # Resume with fixed step implementation: already-done steps should not run again.
        impls_ok = {str(s): ok(str(s)) for s in ORDERED_STEPS}

        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            step_impls=impls_ok,
        )
        db.commit()

        assert r2.status == "done"
        assert calls["market_snapshot_resolve"] == 1
        assert calls["mtm_snapshot"] == 1
        assert calls["pnl_snapshot"] == 2
