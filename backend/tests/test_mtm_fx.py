from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.mtm_service import compute_mtm_for_hedge

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


def test_mtm_with_fx_conversion():
    db = TestingSessionLocal()

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

    # FX
    db.add(
        models.LMEPrice(
            symbol="^USDBRL",
            name="U.S. Dollar/Brazilian Real",
            market="FX",
            price=5.0,
            price_type="close",
            ts_price=datetime.utcnow().astimezone(timezone.utc),
            source="barchart_excel_usdbrl",
        )
    )
    db.commit()

    res = compute_mtm_for_hedge(
        db,
        hedge.id,
        fx_symbol="^USDBRL",
        pricing_source="barchart_excel_usdbrl",
    )
    assert res is not None
    # (2300-2200) * 50 = 5000 USD; FX 5.0 -> 25000 BRL
    assert res.mtm_value == 25000.0
    assert res.fx_rate == 5.0

    db.close()


def test_mtm_with_haircut_scenario():
    db = TestingSessionLocal()

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

    res = compute_mtm_for_hedge(db, hedge.id, pricing_source="yahoo", haircut_pct=10.0)
    assert res is not None
    # Base MTM still 5000; haircut lowers price to 2070 -> scenario becomes negative
    assert res.mtm_value == 5000.0
    assert res.scenario_mtm_value == -6500.0
    db.close()
