from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base

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


def _seed_minimum_contract(db, **overrides):
    deal = models.Deal()
    db.add(deal)
    db.commit()
    db.refresh(deal)

    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number="RFQ-LC-1",
        so_id=1,
        quantity_mt=10.0,
        period="2026-01",
        status=models.RfqStatus.awarded,
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)

    base = dict(
        deal_id=deal.id,
        rfq_id=rfq.id,
        counterparty_id=None,
        status=models.ContractStatus.active.value,
        trade_index=0,
        quote_group_id="g1",
        trade_snapshot={"trade_index": 0, "quote_group_id": "g1", "legs": []},
        settlement_date=None,
        settlement_meta=None,
    )
    base.update(overrides)

    c = models.Contract(**base)
    db.add(c)
    return c


def test_contract_rejects_unknown_status():
    db = TestingSessionLocal()
    with pytest.raises(ValueError, match="Invalid contract status"):
        _seed_minimum_contract(db, status="weird")
    db.close()


def test_contract_settled_requires_settlement_date():
    db = TestingSessionLocal()
    _seed_minimum_contract(db, status=models.ContractStatus.settled.value, settlement_date=None)
    with pytest.raises(ValueError, match="settlement_date is required"):
        db.commit()
    db.close()


def test_contract_settled_accepts_settlement_date():
    db = TestingSessionLocal()
    _seed_minimum_contract(
        db, status=models.ContractStatus.settled.value, settlement_date=date(2026, 1, 31)
    )
    db.commit()

    c = db.query(models.Contract).first()
    assert c is not None
    assert c.status == models.ContractStatus.settled.value
    assert c.settlement_date == date(2026, 1, 31)
    db.close()
