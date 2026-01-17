from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.finance_pipeline_run_service import (
    compute_finance_pipeline_inputs_hash,
    ensure_finance_pipeline_run,
    transition_finance_pipeline_run_status,
)

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


def test_finance_pipeline_inputs_hash_is_deterministic_for_filter_order():
    as_of = date(2026, 1, 16)

    h1 = compute_finance_pipeline_inputs_hash(
        as_of_date=as_of,
        pipeline_version="finance.pipeline.daily.v1.usd_only",
        scope_filters={"deal_id": 10, "contract_id": "abc"},
        mode="materialize",
        emit_exports=True,
    )
    h2 = compute_finance_pipeline_inputs_hash(
        as_of_date=as_of,
        pipeline_version="finance.pipeline.daily.v1.usd_only",
        scope_filters={"contract_id": "abc", "deal_id": 10},
        mode="materialize",
        emit_exports=True,
    )

    assert h1 == h2


def test_ensure_finance_pipeline_run_is_idempotent_by_inputs_hash():
    with TestingSessionLocal() as db:
        r1 = ensure_finance_pipeline_run(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 10},
            mode="materialize",
            emit_exports=True,
            requested_by_user_id=1,
        )
        db.commit()

        assert db.query(models.FinancePipelineRun).count() == 1

        r2 = ensure_finance_pipeline_run(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": 10},
            mode="materialize",
            emit_exports=True,
            requested_by_user_id=1,
        )
        db.commit()

        assert r1.inputs_hash == r2.inputs_hash
        assert r1.id == r2.id
        assert db.query(models.FinancePipelineRun).count() == 1


def test_finance_pipeline_run_status_is_forward_only_and_terminal():
    with TestingSessionLocal() as db:
        run = ensure_finance_pipeline_run(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters=None,
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
        )

        transition_finance_pipeline_run_status(db, run=run, new_status="running")
        transition_finance_pipeline_run_status(db, run=run, new_status="done")
        db.commit()

        assert run.status == "done"

        try:
            transition_finance_pipeline_run_status(db, run=run, new_status="running")
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
