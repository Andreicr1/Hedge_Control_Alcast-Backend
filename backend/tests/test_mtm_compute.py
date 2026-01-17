from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services.mtm_service import compute_mtm_for_hedge


def setup_inmemory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return TestingSessionLocal()


def test_compute_mtm_for_hedge_with_market_price():
    db = setup_inmemory_session()
    cp = models.Counterparty(name="CP-1", type=models.CounterpartyType.bank)
    db.add(cp)
    db.commit()
    db.refresh(cp)

    hedge = models.Hedge(
        so_id=None,
        counterparty_id=cp.id,
        quantity_mt=50.0,
        contract_price=2200.0,
        current_market_price=2300.0,
        period="2025-01",
        instrument="LME-ALU",
        status=models.HedgeStatus.active,
    )
    db.add(hedge)
    db.commit()
    db.refresh(hedge)

    res = compute_mtm_for_hedge(db, hedge.id)
    assert res is not None
    # (2300-2200) * 50 = 5000
    assert res.mtm_value == 5000.0
    assert res.fx_rate is None
    assert res.scenario_mtm_value is None
