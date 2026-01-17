# ruff: noqa: E402

import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

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
from app.services.rfq_transitions import atomic_transition_rfq_status


@pytest.fixture(autouse=True)
def _restore_dependency_overrides():
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides = original


def _make_client_and_sessionmaker():
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


def _seed_minimal_rfq(*, db, status: models.RfqStatus):
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
        customer_id=customer.id,
        total_quantity_mt=10.0,
    )
    so.deal_id = deal.id
    db.add(so)
    db.commit()
    db.refresh(so)

    rfq = models.Rfq(
        rfq_number=f"RFQ-{uid}",
        so_id=so.id,
        quantity_mt=10.0,
        period="Jan/2026",
        status=status,
        message_text="hello",
        created_at=datetime(2026, 1, 1, 0, 0, 0),
    )
    rfq.deal_id = deal.id
    db.add(rfq)
    db.commit()
    db.refresh(rfq)

    return rfq


def test_update_rfq_rejects_status_changes():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        rfq = _seed_minimal_rfq(db=db, status=models.RfqStatus.draft)
        r = client.put(f"/api/rfqs/{rfq.id}", json={"status": "sent"})
        assert r.status_code == 400
    finally:
        db.close()


def test_rfq_webhook_failed_does_not_override_awarded_rfq():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        rfq = _seed_minimal_rfq(db=db, status=models.RfqStatus.awarded)
        attempt = models.RfqSendAttempt(
            rfq_id=rfq.id,
            channel="api",
            status=models.SendStatus.sent,
            provider_message_id="provider-x",
            created_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        db.add(attempt)
        db.commit()

        r = client.post(
            f"/api/rfqs/{rfq.id}/send-attempts/{attempt.id}/status",
            json={"status": "failed", "provider_message_id": "provider-x", "error": "nope"},
        )
        assert r.status_code == 200

        refreshed = db.get(models.Rfq, rfq.id)
        assert refreshed is not None
        assert refreshed.status == models.RfqStatus.awarded

        state_changed = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_STATE_CHANGED")
            .filter(
                models.TimelineEvent.idempotency_key
                == f"rfq:{rfq.id}:state_changed:awarded->failed"
            )
            .all()
        )
        assert len(state_changed) == 0
    finally:
        db.close()


def test_atomic_transition_rejects_out_of_order_concurrent_change():
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        p = Path(tmp_path)
        url = f"sqlite+pysqlite:///{p.as_posix()}"
        engine = create_engine(url, future=True)
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

        with SessionLocal() as db_a:
            rfq = _seed_minimal_rfq(db=db_a, status=models.RfqStatus.draft)
            rfq_id = rfq.id

        with SessionLocal() as db_b:
            transition_b = atomic_transition_rfq_status(
                db=db_b,
                rfq_id=rfq_id,
                to_status=models.RfqStatus.awarded,
                allowed_from={models.RfqStatus.draft},
            )
            assert transition_b.updated is True
            db_b.commit()

        with SessionLocal() as db_a2:
            transition_a = atomic_transition_rfq_status(
                db=db_a2,
                rfq_id=rfq_id,
                to_status=models.RfqStatus.sent,
                allowed_from={models.RfqStatus.draft},
            )
            assert transition_a.updated is False
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
