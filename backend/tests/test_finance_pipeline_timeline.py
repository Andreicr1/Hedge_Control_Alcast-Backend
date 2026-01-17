from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.finance_pipeline_daily import ORDERED_STEPS, execute_finance_pipeline_daily
from app.services.finance_pipeline_timeline import finance_pipeline_idempotency_key

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


def _mk_impls(calls: dict[str, int], *, fail_step: str | None = None):
    def ok(step_name: str):
        def _impl(_db, _plan, _run):
            calls[step_name] += 1

        return _impl

    def boom(_db, _plan, _run):
        assert fail_step is not None
        calls[fail_step] += 1
        raise RuntimeError("kaboom")

    impls = {str(s): ok(str(s)) for s in ORDERED_STEPS}
    if fail_step is not None:
        impls[fail_step] = boom
    return impls


def _count_event(db, event_type: str) -> int:
    return (
        db.query(models.TimelineEvent).filter(models.TimelineEvent.event_type == event_type).count()
    )


def test_finance_pipeline_timeline_rerun_does_not_duplicate_events():
    with TestingSessionLocal() as db:
        calls = {str(s): 0 for s in ORDERED_STEPS}
        impls = _mk_impls(calls)

        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-000000000001",
            step_impls=impls,
        )

        assert r1.status == "done"
        run = db.query(models.FinancePipelineRun).first()
        assert run is not None

        assert _count_event(db, "FINANCE_PIPELINE_REQUESTED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_STARTED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_COMPLETED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_FAILED") == 0

        # idempotency_key contract is exact
        started = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "FINANCE_PIPELINE_STARTED")
            .first()
        )
        assert started is not None
        assert started.idempotency_key == finance_pipeline_idempotency_key(
            event="started", inputs_hash=str(run.inputs_hash)
        )

        # Re-run is a no-op once the run is done; must not add events.
        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-000000000001",
            step_impls=impls,
        )

        assert r2.inputs_hash == r1.inputs_hash
        assert db.query(models.TimelineEvent).count() == 3
        assert _count_event(db, "FINANCE_PIPELINE_STARTED") == 1


def test_finance_pipeline_timeline_failed_resume_completed_has_no_double_started():
    with TestingSessionLocal() as db:
        calls = {str(s): 0 for s in ORDERED_STEPS}

        impls_fail = _mk_impls(calls, fail_step="pnl_snapshot")
        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-000000000002",
            step_impls=impls_fail,
        )

        assert r1.status == "failed"
        assert _count_event(db, "FINANCE_PIPELINE_REQUESTED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_STARTED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_FAILED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_COMPLETED") == 0

        impls_ok = _mk_impls(calls)
        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-000000000002",
            step_impls=impls_ok,
        )

        assert r2.status == "done"
        assert _count_event(db, "FINANCE_PIPELINE_REQUESTED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_STARTED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_FAILED") == 1
        assert _count_event(db, "FINANCE_PIPELINE_COMPLETED") == 1
        assert db.query(models.TimelineEvent).count() == 4
