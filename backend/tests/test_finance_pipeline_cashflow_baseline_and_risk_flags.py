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


def _seed_contract(db, *, settlement_date: date | None):
    deal = models.Deal(commodity="AL", currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number="RFQ-CF-1",
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
        settlement_date=settlement_date,
        settlement_meta=None,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    return deal, rfq, contract


def _seed_mtm_contract_snapshot(db, *, contract: models.Contract, as_of_date: date):
    run = models.MtmContractSnapshotRun(
        as_of_date=as_of_date,
        scope_filters={"deal_id": int(contract.deal_id)},
        inputs_hash="mtmhash",
        requested_by_user_id=None,
    )
    db.add(run)
    db.flush()

    snap = models.MtmContractSnapshot(
        run_id=int(run.id),
        as_of_date=as_of_date,
        contract_id=str(contract.contract_id),
        deal_id=int(contract.deal_id),
        currency="USD",
        mtm_usd=123.4,
        methodology="test",
        references={
            "as_of_date": as_of_date.isoformat(),
            "methodology": "test",
            "price_used": 2100.0,
            "observation_start": "2026-01-10",
            "observation_end_used": "2026-01-15",
            "last_published_cash_date": "2026-01-15",
        },
        inputs_hash="mtmhash",
    )
    db.add(snap)
    db.flush()

    return run, snap


def _seed_pnl_contract_snapshot(db, *, contract: models.Contract, as_of_date: date):
    run = models.PnlSnapshotRun(
        as_of_date=as_of_date,
        scope_filters={"deal_id": int(contract.deal_id)},
        inputs_hash="pnlhash",
        requested_by_user_id=None,
    )
    db.add(run)
    db.flush()

    snap = models.PnlContractSnapshot(
        run_id=int(run.id),
        as_of_date=as_of_date,
        contract_id=str(contract.contract_id),
        deal_id=int(contract.deal_id),
        currency="USD",
        unrealized_pnl_usd=50.0,
        methodology="test",
        data_quality_flags=[],
        inputs_hash="pnlhash",
    )
    db.add(snap)
    db.flush()

    return run, snap


def test_pipeline_cashflow_baseline_and_risk_flags_idempotent_when_inputs_available():
    def _noop(_db, _plan, _run):
        return None

    step_impls = {
        "market_snapshot_resolve": _noop,
        "mtm_snapshot": _noop,
        "pnl_snapshot": _noop,
        # cashflow_baseline omitted: uses default implementation
        # risk_flags omitted: uses default implementation
        "exports": _noop,
    }

    with TestingSessionLocal() as db:
        deal, _rfq, contract = _seed_contract(db, settlement_date=date(2026, 1, 22))
        _seed_mtm_contract_snapshot(db, contract=contract, as_of_date=date(2026, 1, 16))
        _seed_pnl_contract_snapshot(db, contract=contract, as_of_date=date(2026, 1, 16))
        db.commit()

        r1 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": int(deal.id)},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000d001",
            step_impls=step_impls,
        )
        db.commit()

        assert db.query(models.CashflowBaselineRun).count() == 1
        assert db.query(models.CashflowBaselineItem).count() == 1
        assert db.query(models.FinanceRiskFlagRun).count() == 1
        assert db.query(models.FinanceRiskFlag).count() == 0

        cf_step = (
            db.query(models.FinancePipelineStep)
            .filter(models.FinancePipelineStep.run_id == int(r1.run_id))
            .filter(models.FinancePipelineStep.step_name == "cashflow_baseline")
            .first()
        )
        assert cf_step is not None
        assert cf_step.artifacts is not None
        assert int(cf_step.artifacts["cashflow_baseline_run_id"]) > 0
        assert len(str(cf_step.artifacts["cashflow_baseline_inputs_hash"])) == 64
        assert isinstance(cf_step.artifacts["cashflow_baseline_item_ids"], list)
        assert len(cf_step.artifacts["cashflow_baseline_item_ids"]) == 1

        rf_step = (
            db.query(models.FinancePipelineStep)
            .filter(models.FinancePipelineStep.run_id == int(r1.run_id))
            .filter(models.FinancePipelineStep.step_name == "risk_flags")
            .first()
        )
        assert rf_step is not None
        assert rf_step.artifacts is not None
        assert int(rf_step.artifacts["finance_risk_flags_run_id"]) > 0
        assert len(str(rf_step.artifacts["finance_risk_flags_inputs_hash"])) == 64
        assert isinstance(rf_step.artifacts["finance_risk_flag_ids"], list)
        assert len(rf_step.artifacts["finance_risk_flag_ids"]) == 0

        r2 = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": int(deal.id)},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000d002",
            step_impls=step_impls,
        )
        db.commit()

        assert r2.inputs_hash == r1.inputs_hash
        assert db.query(models.CashflowBaselineRun).count() == 1
        assert db.query(models.CashflowBaselineItem).count() == 1
        assert db.query(models.FinanceRiskFlagRun).count() == 1
        assert db.query(models.FinanceRiskFlag).count() == 0


def test_pipeline_risk_flags_created_when_inputs_missing_and_settlement_date_missing():
    def _noop(_db, _plan, _run):
        return None

    step_impls = {
        "market_snapshot_resolve": _noop,
        "mtm_snapshot": _noop,
        "pnl_snapshot": _noop,
        # cashflow_baseline omitted: uses default implementation
        # risk_flags omitted: uses default implementation
        "exports": _noop,
    }

    with TestingSessionLocal() as db:
        deal, _rfq, _contract = _seed_contract(db, settlement_date=None)

        _ = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": int(deal.id)},
            mode="materialize",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000d003",
            step_impls=step_impls,
        )
        db.commit()

        assert db.query(models.CashflowBaselineRun).count() == 1
        assert db.query(models.CashflowBaselineItem).count() == 1
        assert db.query(models.FinanceRiskFlagRun).count() == 1

        # missing_settlement_date + mtm_not_available + pnl_not_available + data_incomplete
        assert db.query(models.FinanceRiskFlag).count() == 4


def test_pipeline_dry_run_does_not_write_cashflow_baseline_or_risk_flags():
    with TestingSessionLocal() as db:
        deal, _rfq, _contract = _seed_contract(db, settlement_date=None)

        _ = execute_finance_pipeline_daily(
            db,
            as_of_date=date(2026, 1, 16),
            pipeline_version="finance.pipeline.daily.v1.usd_only",
            scope_filters={"deal_id": int(deal.id)},
            mode="dry_run",
            emit_exports=False,
            requested_by_user_id=1,
            request_id="00000000-0000-0000-0000-00000000d004",
            step_impls=None,
        )

        assert db.query(models.CashflowBaselineRun).count() == 0
        assert db.query(models.CashflowBaselineItem).count() == 0
        assert db.query(models.FinanceRiskFlagRun).count() == 0
        assert db.query(models.FinanceRiskFlag).count() == 0
