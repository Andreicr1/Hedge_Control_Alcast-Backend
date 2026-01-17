# ruff: noqa: E402, I001, E501

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

from app.database import Base
from app.api import deps
from app import models
from app.main import app


@pytest.fixture(autouse=True)
def _restore_dependency_overrides():
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides = original


def _make_client_and_sessionmaker():
    # Isolate overrides from other test modules.
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

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    return TestClient(app), TestingSessionLocal


def test_mtm_record_created_emits_idempotent_timeline_and_is_labeled_proxy():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    request_id = str(uuid.uuid4())
    payload = {
        "as_of_date": "2026-01-12",
        "object_type": "hedge",
        "object_id": 123,
        "forward_price": 2100.0,
        "fx_rate": None,
        "mtm_value": 1000.0,
        "methodology": "unit.test",
    }

    r1 = client.post("/api/mtm", json=payload, headers={"X-Request-ID": request_id})
    r2 = client.post("/api/mtm", json=payload, headers={"X-Request-ID": request_id})
    assert r1.status_code == 201
    assert r2.status_code == 201

    body = r1.json()
    assert body["institutional_layer"] == "proxy"
    assert body["is_proxy"] is True

    db = TestingSessionLocal()
    try:
        events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "MTM_RECORD_CREATED")
            .all()
        )
        assert len(events) == 1
        assert events[0].correlation_id == str(uuid.UUID(request_id))
        assert events[0].payload["institutional_layer"] == "proxy"
    finally:
        db.close()


def test_mtm_snapshot_created_emits_idempotent_timeline_and_is_labeled_proxy():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        cp = models.Counterparty(name="CP-1", type=models.CounterpartyType.bank)
        db.add(cp)
        db.commit()
        db.refresh(cp)

        hedge = models.Hedge(
            so_id=None,
            counterparty_id=cp.id,
            quantity_mt=10.0,
            contract_price=2000.0,
            period="2026-01",
        )
        db.add(hedge)
        db.commit()
        db.refresh(hedge)
    finally:
        db.close()

    request_id = str(uuid.uuid4())
    payload = {
        "object_type": "hedge",
        "object_id": hedge.id,
        "price": 2100.0,
        "as_of_date": "2026-01-12",
    }

    r1 = client.post("/api/mtm/snapshots", json=payload, headers={"X-Request-ID": request_id})
    r2 = client.post("/api/mtm/snapshots", json=payload, headers={"X-Request-ID": request_id})
    assert r1.status_code == 201
    assert r2.status_code == 201

    body = r1.json()
    assert body["institutional_layer"] == "proxy"
    assert body["is_proxy"] is True

    db = TestingSessionLocal()
    try:
        events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "MTM_SNAPSHOT_CREATED")
            .all()
        )
        assert len(events) == 1
        assert events[0].correlation_id == str(uuid.UUID(request_id))
        assert events[0].payload["institutional_layer"] == "proxy"
    finally:
        db.close()
