# ruff: noqa: E402

import os
import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

from app import models
from app.api import deps
from app.database import Base
from app.main import app


@pytest.fixture(autouse=True)
def _restore_dependency_overrides():
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides = original


def _make_client_and_sessionmaker(role: models.RoleName = models.RoleName.financeiro):
    # Isolate from other test modules that mutate app.dependency_overrides.
    app.dependency_overrides = {}

    engine = create_engine(
        os.environ["DATABASE_URL"],
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_db] = override_get_db

    def _stub_user(role_name: models.RoleName):
        class StubUser:
            def __init__(self):
                self.id = 1
                self.email = f"{role_name.value}@test.com"
                self.active = True
                self.role = type("Role", (), {"name": role_name})()

        return StubUser()

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(role)

    return TestClient(app), TestingSessionLocal


def _seed_minimal_dashboard_data(db):
    uid = uuid.uuid4().hex[:8]

    deal = models.Deal(currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    customer = models.Customer(name=f"Cliente-{uid}")
    db.add(customer)
    db.commit()
    db.refresh(customer)

    so = models.SalesOrder(
        so_number=f"SO-{uid}",
        deal_id=deal.id,
        customer_id=customer.id,
        total_quantity_mt=10.0,
        product="AL",
    )
    db.add(so)
    db.commit()
    db.refresh(so)

    rfq = models.Rfq(
        deal_id=deal.id,
        rfq_number=f"RFQ-{uid}",
        so_id=so.id,
        quantity_mt=10.0,
        period="2026-01",
        status=models.RfqStatus.pending,
        created_at=datetime.utcnow(),
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)

    # Contract invariants require a non-empty trade_snapshot.
    contract = models.Contract(
        deal_id=deal.id,
        rfq_id=rfq.id,
        status=models.ContractStatus.active.value,
        settlement_date=date.today(),
        trade_snapshot={
            "legs": [
                {
                    "price_type": "FIX",
                    "price": 2000.0,
                    "side": "buy",
                    "volume_mt": 10.0,
                }
            ]
        },
        created_at=datetime.utcnow(),
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)

    ev = models.TimelineEvent(
        event_type="rfq.created",
        occurred_at=datetime.utcnow(),
        subject_type="rfq",
        subject_id=rfq.id,
        correlation_id=str(uuid.uuid4()),
        visibility="finance",
        payload={"rfq_id": rfq.id},
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    return {
        "customer": customer,
        "so": so,
        "rfq": rfq,
        "contract": contract,
        "event": ev,
    }


def test_dashboard_summary_is_db_backed_and_shape_is_stable():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)
    db = SessionLocal()
    try:
        seeded = _seed_minimal_dashboard_data(db)

        r = client.get("/api/dashboard/summary")
        assert r.status_code == 200
        data = r.json()

        # Shape (frontend compatibility)
        for k in ["mtm", "settlements", "rfqs", "contracts", "timeline", "lastUpdated"]:
            assert k in data

        # Not mocked: seeded IDs must show up.
        rfq_ids = {item.get("id") for item in data["rfqs"]}
        assert str(seeded["rfq"].id) in rfq_ids

        contract_ids = {item.get("id") for item in data["contracts"]}
        assert str(seeded["contract"].contract_id) in contract_ids

        timeline_ids = {item.get("id") for item in data["timeline"]}
        assert str(seeded["event"].id) in timeline_ids

        # Settlements reflect contracts settling today (even if computed amount is 0.0)
        assert data["settlements"]["count"] == 1
        assert data["settlements"]["currency"] == "USD"

    finally:
        db.close()


def test_dashboard_summary_allows_admin():
    # Admin is now allowed to access dashboard summary
    client, _ = _make_client_and_sessionmaker(models.RoleName.admin)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
