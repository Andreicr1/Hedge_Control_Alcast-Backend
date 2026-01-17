from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.mtm_snapshot_service import list_snapshots

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


def test_list_snapshots_latest_is_deterministic_on_created_at_ties():
    db = TestingSessionLocal()

    # Force a created_at tie; ordering must still be deterministic.
    ts = datetime(2026, 1, 12, 12, 0, 0)

    s1 = models.MTMSnapshot(
        object_type=models.MarketObjectType.net,
        object_id=None,
        product="AL",
        period="2026-01",
        price=2000.0,
        quantity_mt=10.0,
        mtm_value=20000.0,
        as_of_date=date(2026, 1, 12),
        created_at=ts,
    )
    db.add(s1)
    db.commit()

    s2 = models.MTMSnapshot(
        object_type=models.MarketObjectType.net,
        object_id=None,
        product="AL",
        period="2026-01",
        price=2100.0,
        quantity_mt=10.0,
        mtm_value=21000.0,
        as_of_date=date(2026, 1, 12),
        created_at=ts,
    )
    db.add(s2)
    db.commit()

    latest = list_snapshots(
        db,
        object_type=models.MarketObjectType.net,
        object_id=None,
        product="AL",
        period="2026-01",
        latest=True,
    )
    assert len(latest) == 1
    assert latest[0].id == s2.id

    all_snaps = list_snapshots(
        db,
        object_type=models.MarketObjectType.net,
        object_id=None,
        product="AL",
        period="2026-01",
        latest=False,
    )
    assert [s.id for s in all_snaps] == [s2.id, s1.id]

    db.close()
