from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.pnl_snapshot_service import compute_pnl_inputs_hash, execute_pnl_snapshot_run

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
        rfq_number="RFQ-PNL-1",
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


def _seed_avg_settled_contract(db):
    deal = models.Deal(commodity="AL", currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number="RFQ-PNL-2",
        so_id=1,
        quantity_mt=1.0,
        period="2025-12",
        status=models.RfqStatus.awarded,
        trade_specs=[
            {
                "trade_type": "Swap",
                "leg1": {
                    "side": "buy",
                    "price_type": "Fix",
                    "quantity_mt": 1.0,
                    "fixing_date": "2025-12-31",
                },
                "leg2": {
                    "side": "sell",
                    "price_type": "AVG",
                    "quantity_mt": 1.0,
                    "month_name": "December",
                    "year": 2025,
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
        status=models.ContractStatus.settled.value,
        trade_index=0,
        quote_group_id="g2",
        trade_snapshot={
            "trade_index": 0,
            "quote_group_id": "g2",
            "legs": [
                {"side": "buy", "price": 2000.0, "volume_mt": 1.0, "price_type": "Fix"},
                {"side": "sell", "price": 0.0, "volume_mt": 1.0, "price_type": "AVG"},
            ],
        },
        settlement_date=date(2026, 1, 5),
        settlement_meta=None,
    )
    db.add(contract)

    for day in range(1, 32):
        as_of = datetime(2025, 12, day, 0, 0, 0, tzinfo=timezone.utc)
        db.add(
            models.MarketPrice(
                source="westmetall",
                symbol="ALUMINUM_CASH_SETTLEMENT",
                contract_month=None,
                price=3000.0,
                currency="USD",
                as_of=as_of,
                fx=False,
            )
        )

    db.commit()
    db.refresh(contract)
    return deal, rfq, contract


def test_pnl_inputs_hash_is_deterministic_for_filter_order():
    as_of = date(2026, 1, 16)

    h1 = compute_pnl_inputs_hash(as_of_date=as_of, filters={"deal_id": 10, "contract_id": "abc"})
    h2 = compute_pnl_inputs_hash(as_of_date=as_of, filters={"contract_id": "abc", "deal_id": 10})
    assert h1 == h2


def test_pnl_dry_run_does_not_write_any_tables():
    with TestingSessionLocal() as db:
        _seed_avginter_active_contract(db)

        res = execute_pnl_snapshot_run(
            db,
            as_of_date=date(2026, 1, 16),
            filters=None,
            requested_by_user_id=1,
            dry_run=True,
        )

        assert res.active_contracts == 1
        assert len(res.unrealized_preview) == 1

        assert db.query(models.PnlSnapshotRun).count() == 0
        assert db.query(models.PnlContractSnapshot).count() == 0
        assert db.query(models.PnlContractRealized).count() == 0


def test_pnl_materialize_is_idempotent_by_inputs_hash():
    with TestingSessionLocal() as db:
        _seed_avginter_active_contract(db)

        r1 = execute_pnl_snapshot_run(
            db,
            as_of_date=date(2026, 1, 16),
            filters=None,
            requested_by_user_id=1,
            dry_run=False,
        )
        db.commit()

        assert db.query(models.PnlSnapshotRun).count() == 1
        assert db.query(models.PnlContractSnapshot).count() == 1

        r2 = execute_pnl_snapshot_run(
            db,
            as_of_date=date(2026, 1, 16),
            filters=None,
            requested_by_user_id=1,
            dry_run=False,
        )
        db.commit()

        assert r1.inputs_hash == r2.inputs_hash
        assert db.query(models.PnlSnapshotRun).count() == 1
        assert db.query(models.PnlContractSnapshot).count() == 1


def test_pnl_realized_lock_is_created_for_settled_contract():
    with TestingSessionLocal() as db:
        _seed_avg_settled_contract(db)

        _ = execute_pnl_snapshot_run(
            db,
            as_of_date=date(2026, 1, 10),
            filters=None,
            requested_by_user_id=1,
            dry_run=False,
        )
        db.commit()

        locks = db.query(models.PnlContractRealized).all()
        assert len(locks) == 1
        lock = locks[0]
        assert lock.realized_pnl_usd == (3000.0 - 2000.0) * 1.0
        assert lock.locked_at is not None
        assert lock.currency == "USD"
