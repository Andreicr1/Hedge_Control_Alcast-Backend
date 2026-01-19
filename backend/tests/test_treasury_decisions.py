# ruff: noqa: E402

import os
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from app import models
from app.api import deps
from app.database import Base
from app.main import app

engine = create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _stub_user(role_name: models.RoleName):
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


client = TestClient(app)


def _seed_exposure_so(*, customer_kyc_status: str | None):
    db = TestingSessionLocal()
    try:
        uid = uuid.uuid4().hex[:8]
        deal = models.Deal(currency="USD")
        db.add(deal)
        db.commit()
        db.refresh(deal)

        customer = models.Customer(name=f"Cliente {uid}")
        customer.kyc_status = customer_kyc_status
        db.add(customer)
        db.commit()
        db.refresh(customer)

        so = models.SalesOrder(
            so_number=f"SO-{uid}",
            customer_id=customer.id,
            total_quantity_mt=10.0,
        )
        so.deal_id = deal.id
        db.add(so)
        db.commit()
        db.refresh(so)

        exposure = models.Exposure(
            source_type=models.MarketObjectType.so,
            source_id=so.id,
            exposure_type=models.ExposureType.active,
            quantity_mt=10.0,
        )
        db.add(exposure)
        db.commit()
        db.refresh(exposure)
        return exposure.id
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _restore_dependency_overrides():
    original = dict(app.dependency_overrides)
    # Ensure our DB override is active for every test in this module.
    app.dependency_overrides[deps.get_db] = override_get_db
    try:
        yield
    finally:
        app.dependency_overrides = original


def test_finance_can_create_decision_even_if_kyc_pending():
    exposure_id = _seed_exposure_so(customer_kyc_status="pending")

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    r = client.post(
        "/api/treasury/decisions",
        json={
            "exposure_id": exposure_id,
            "decision_kind": "hedge",
            "notes": "Decision recorded even with KYC pending",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exposure_id"] == exposure_id
    assert body["decision_kind"] == "hedge"
    assert body["kyc_gate"]["allowed"] is False
    assert body["kyc_state"] == "needs_override"
    assert body["kyc_requires_override"] is True
    assert body["kyc_override"] is None


def test_auditoria_cannot_create_decision_but_can_list():
    exposure_id = _seed_exposure_so(customer_kyc_status="approved")

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.auditoria)

    r_create = client.post(
        "/api/treasury/decisions",
        json={"exposure_id": exposure_id, "decision_kind": "hedge"},
    )
    assert r_create.status_code == 403

    r_list = client.get("/api/treasury/decisions", params={"exposure_id": exposure_id})
    assert r_list.status_code == 200, r_list.text
    assert "items" in r_list.json()


def test_admin_can_create_kyc_override():
    exposure_id = _seed_exposure_so(customer_kyc_status="pending")

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)
    r = client.post(
        "/api/treasury/decisions",
        json={"exposure_id": exposure_id, "decision_kind": "hedge"},
    )
    assert r.status_code == 200, r.text
    decision_id = r.json()["id"]

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.admin)
    r2 = client.post(
        f"/api/treasury/decisions/{decision_id}/kyc-overrides",
        json={"reason": "Non-blocking override recorded for audit"},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["id"] == decision_id
    assert body["kyc_override"]["reason"] == "Non-blocking override recorded for audit"
    assert body["kyc_state"] == "overridden"
    assert body["kyc_requires_override"] is False
