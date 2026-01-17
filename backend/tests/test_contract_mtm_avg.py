from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.contract_mtm_service import compute_mtm_for_contract_avg

# Isolated in-memory DB
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


def test_contract_mtm_avginter_uses_realized_avg_until_yesterday():
    db = TestingSessionLocal()

    # Minimal RFQ + Contract wiring (SQLite doesn't enforce FKs by default in tests)
    deal = models.Deal()
    db.add(deal)
    db.commit()
    db.refresh(deal)

    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number="RFQ-1",
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
        status="active",
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

    # Official Cash-Settlement for days 10..15 inclusive (so on day 16, realized avg uses 10..15)
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

    res = compute_mtm_for_contract_avg(db, contract, as_of_date=date(2026, 1, 16))
    assert res is not None
    # Realized avg across 10..15 is 2100; fixed_leg is BUY => (avg - fixed) * qty
    assert res.price_used == 2100.0
    assert res.mtm_usd == (2100.0 - 2000.0) * 10.0

    db.close()


def test_monthly_average_matches_daily_average_when_month_complete():
    db = TestingSessionLocal()

    deal = models.Deal()
    db.add(deal)
    db.commit()
    db.refresh(deal)

    # AVG month: December 2025
    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number="RFQ-2",
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
        status="active",
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
        settlement_date=None,
        settlement_meta=None,
    )
    db.add(contract)

    # Simulate a "complete month" with daily settlements at 3000 for all 31 days.
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

    from app.services.contract_mtm_service import compute_final_avg_cash

    avg, last_pub = compute_final_avg_cash(db, date(2025, 12, 1), date(2025, 12, 31))
    assert last_pub == date(2025, 12, 31)
    assert avg == 3000.0

    db.close()


def test_contract_mtm_returns_none_for_non_active_contract():
    db = TestingSessionLocal()

    deal = models.Deal()
    db.add(deal)
    db.commit()
    db.refresh(deal)

    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number="RFQ-3",
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
        status=models.ContractStatus.settled.value,
        trade_index=0,
        quote_group_id="g3",
        trade_snapshot={
            "trade_index": 0,
            "quote_group_id": "g3",
            "legs": [
                {"side": "buy", "price": 2000.0, "volume_mt": 10.0, "price_type": "Fix"},
                {"side": "sell", "price": 0.0, "volume_mt": 10.0, "price_type": "AVGInter"},
            ],
        },
        settlement_date=date(2026, 1, 31),
        settlement_meta=None,
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    # Even with market prices available, institutional rule blocks MTM for non-active contracts.
    res = compute_mtm_for_contract_avg(db, contract, as_of_date=date(2026, 1, 16))
    assert res is None

    db.close()
