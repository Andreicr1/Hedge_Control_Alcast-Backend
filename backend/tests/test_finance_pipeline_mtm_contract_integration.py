from __future__ import annotations

from datetime import date, datetime, timezone

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


def _seed_avginter_active_contract(db):
    deal = models.Deal(commodity="AL", currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number="RFQ-MTM-1",
        so_id=1,
        quantity_mt=10.0,
        period="2026-01",
        status=models.RfqStatus.awarded,
        trade_specs=[
            {
                "trade_type": "Swap",
                "leg1": {
                    "side": "buy",
                    "price_type": "Fix",
                    "quantity_mt": 10.0,
                    "fixing_date": "2026-01-15",
                },
                "leg2": {
                    "side": "sell",
                    "price_type": "AVGInter",
                    "quantity_mt": 10.0,
                    "start_date": "2026-01-10",
                    "end_date": "2026-01-20",
                },
                "sync_ppt": False,
            }
        ],
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)

    contract = models.Contract(
        deal_id=deal.id,
        rfq_id=rfq.id,
        counterparty_id=None,
        status=models.ContractStatus.active.value,
        trade_index=0,
        quote_group_id="g1",
        trade_snapshot={
            "trade_index": 0,
            "quote_group_id": "g1",
            "legs": [
                {"side": "buy", "price": 2000.0, "volume_mt": 10.0, "price_type": "Fix"},
                {"side": "sell", "price": 0.0, "volume_mt": 10.0, "price_type": "AVGInter"},
            ],
        },
        settlement_date=None,
        settlement_meta=None,
    )
    db.add(contract)

    settled_contract = models.Contract(
        deal_id=deal.id,
        rfq_id=rfq.id,
        counterparty_id=None,
        status=models.ContractStatus.settled.value,
        trade_index=1,
        quote_group_id="g1",
        trade_snapshot={
            "trade_index": 1,
            "quote_group_id": "g1",
            "legs": [
                {"side": "buy", "price": 2000.0, "volume_mt": 1.0, "price_type": "Fix"},
                {"side": "sell", "price": 0.0, "volume_mt": 1.0, "price_type": "AVGInter"},
            ],
        },
        settlement_date=date(2026, 1, 22),
        settlement_meta=None,
    )
    db.add(settled_contract)

    for day in range(10, 16):
        as_of = datetime(2026, 1, day, 0, 0, 0, tzinfo=timezone.utc)
        db.add(
            models.MarketPrice(
                source="westmetall",
                symbol="ALUMINUM_CASH_SETTLEMENT",
                contract_month=None,
                price=2100.0,
                currency="USD",
                as_of=as_of,
                fx=False,
            )
        )

    db.commit()
    db.refresh(contract)
    return deal, rfq, contract


def test_pipeline_mtm_contract_snapshot_active_only_idempotent_and_no_proxy_usage():
    def _noop(_db, _plan, _run):
        return None

    step_impls = {
        "market_snapshot_resolve": _noop,
        # "mtm_snapshot" intentionally omitted: uses default contract-only integration
        "pnl_snapshot": _noop,
        "cashflow_baseline": _noop,
        "risk_flags": _noop,
        "exports": _noop,
    }

    with TestingSessionLocal() as db:
        deal, _rfq, _contract = _seed_avginter_active_contract(db)

        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": int(deal.id)},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000c001",
            step_impls=step_impls,
        )
        db.commit()

        assert db.query(models.MtmContractSnapshotRun).count() == 1
        assert db.query(models.MtmContractSnapshot).count() == 1  # active only
        assert db.query(models.MTMSnapshot).count() == 0  # proxy snapshots must not be used

        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "MTM_SNAPSHOT_CREATED")
            .count()
            == 1
        )

        step = (
            db.query(models.FinancePipelineStep)
            .filter(models.FinancePipelineStep.run_id == int(r1.run_id))
            .filter(models.FinancePipelineStep.step_name == "mtm_snapshot")
            .first()
        )
        assert step is not None
        assert step.artifacts is not None
        assert int(step.artifacts["mtm_contract_snapshot_run_id"]) > 0
        assert isinstance(step.artifacts["mtm_inputs_hash"], str)
        assert len(step.artifacts["mtm_inputs_hash"]) == 64
        assert isinstance(step.artifacts["mtm_contract_snapshot_ids"], list)
        assert len(step.artifacts["mtm_contract_snapshot_ids"]) == 1

        # Re-run should be idempotent: no new snapshots or timeline events.
        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": int(deal.id)},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000c002",
            step_impls=step_impls,
        )
        db.commit()

        assert r2.inputs_hash == r1.inputs_hash
        assert db.query(models.MtmContractSnapshotRun).count() == 1
        assert db.query(models.MtmContractSnapshot).count() == 1
        assert db.query(models.MTMSnapshot).count() == 0
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "MTM_SNAPSHOT_CREATED")
            .count()
            == 1
        )


def test_pipeline_dry_run_does_not_write_mtm_contract_snapshot_or_timeline_or_proxy():
    with TestingSessionLocal() as db:
        deal, _rfq, _contract = _seed_avginter_active_contract(db)

        _ = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": int(deal.id)},
            mode="dry_run",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000c003",
            step_impls=None,
        )

        assert db.query(models.MtmContractSnapshotRun).count() == 0
        assert db.query(models.MtmContractSnapshot).count() == 0
        assert db.query(models.MTMSnapshot).count() == 0
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "MTM_SNAPSHOT_CREATED")
            .count()
            == 0
        )
