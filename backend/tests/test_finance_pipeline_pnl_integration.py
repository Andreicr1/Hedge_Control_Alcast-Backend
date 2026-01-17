from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
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


def test_pipeline_pnl_snapshot_is_idempotent_and_emits_single_timeline_event():
    def _noop(_db, _plan, _run):
        return None

    step_impls = {
        "market_snapshot_resolve": _noop,
        "mtm_snapshot": _noop,
        # "pnl_snapshot" intentionally omitted: uses default integration
        "cashflow_baseline": _noop,
        "risk_flags": _noop,
        "exports": _noop,
    }

    with TestingSessionLocal() as db:
        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 10},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000b001",
            step_impls=step_impls,
        )
        db.commit()

        assert r1.status in {"running", "done", "failed"}
        assert db.query(models.PnlSnapshotRun).count() == 1
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "PNL_SNAPSHOT_CREATED")
            .count()
            == 1
        )

        step = (
            db.query(models.FinancePipelineStep)
            .filter(models.FinancePipelineStep.run_id == int(r1.run_id))
            .filter(models.FinancePipelineStep.step_name == "pnl_snapshot")
            .first()
        )
        assert step is not None
        assert step.artifacts is not None
        assert int(step.artifacts["pnl_snapshot_run_id"]) > 0
        assert isinstance(step.artifacts["pnl_inputs_hash"], str)
        assert len(step.artifacts["pnl_inputs_hash"]) == 64

        # Second run should be idempotent: no new P&L snapshot run or timeline event.
        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 10},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000b002",
            step_impls=step_impls,
        )
        db.commit()

        assert r2.inputs_hash == r1.inputs_hash
        assert db.query(models.PnlSnapshotRun).count() == 1
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "PNL_SNAPSHOT_CREATED")
            .count()
            == 1
        )


def test_pipeline_dry_run_does_not_write_pnl_snapshot_or_timeline():
    with TestingSessionLocal() as db:
        _ = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 10},
            mode="dry_run",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000b003",
            step_impls=None,
        )

        assert db.query(models.PnlSnapshotRun).count() == 0
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "PNL_SNAPSHOT_CREATED")
            .count()
            == 0
        )
