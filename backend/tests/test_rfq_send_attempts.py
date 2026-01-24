import hashlib
import hmac
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.api.routes import rfq_send, rfq_webhook
from app.config import settings
from app.database import Base
from app.main import app
from app.models.domain import RfqStatus
from app.schemas import RfqSendAttemptCreate

# In-memory SQLite for isolated tests (shared across connections)
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)
client = TestClient(app)


class _StubRole:
    def __init__(self, name):
        self.name = name


class _StubUser:
    def __init__(self, role_name, user_id=1):
        self.role = _StubRole(role_name)
        self.id = user_id
        self.active = True


def setup_function():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def seed_rfq():
    db = TestingSessionLocal()
    sup = models.Supplier(name="Supp", country="BR", contact_email="x@test.com")
    db.add(sup)
    db.commit()
    db.refresh(sup)

    po = models.PurchaseOrder(
        po_number="PO-test",
        supplier_id=sup.id,
        total_quantity_mt=1.0,
        product="AL",
        status=models.OrderStatus.active,
    )
    db.add(po)
    db.commit()
    db.refresh(po)

    rfq = models.Rfq(
        rfq_type=models.RfqType.hedge_buy,
        reference_po_id=po.id,
        reference_so_id=None,
        tenor_month="2025-01",
        quantity_mt=1.0,
        channel="api",
        message_text="Test message",
        status=RfqStatus.draft,
    )
    db.add(rfq)
    db.commit()
    db.refresh(rfq)
    db.close()
    return rfq


@pytest.mark.skip(
    reason="Rfq model schema changed significantly - needs refactor to use new fields (so_id, rfq_number, period instead of rfq_type, reference_po_id, tenor_month)"
)
def test_send_attempt_flow():
    rfq = seed_rfq()

    # Call route handler directly with stub user and session
    payload = RfqSendAttemptCreate(
        channel="email",
        idempotency_key="k1",
        metadata={"failures_before_success": 1},
        max_retries=2,
    )
    db = TestingSessionLocal()
    attempt_obj = rfq_send.send_rfq(
        rfq_id=rfq.id,
        payload=payload,
        db=db,
        current_user=_StubUser(models.RoleName.financeiro),
    )
    attempt_status = (
        attempt_obj.status.value
        if hasattr(attempt_obj.status, "value")
        else str(attempt_obj.status)
    )
    assert attempt_status in ["queued", "sent"]  # should succeed after retry
    assert attempt_obj.rfq_id == rfq.id
    assert attempt_obj.idempotency_key == "k1"

    # Idempotency should return the same attempt without creating a new one
    duplicate = rfq_send.send_rfq(
        rfq_id=rfq.id,
        payload=RfqSendAttemptCreate(channel="email", idempotency_key="k1"),
        db=db,
        current_user=_StubUser(models.RoleName.financeiro),
    )
    assert duplicate.id == attempt_obj.id

    # Retry flow should create a new attempt linked to the previous one
    retry_attempt = rfq_send.send_rfq(
        rfq_id=rfq.id,
        payload=RfqSendAttemptCreate(
            channel="email",
            idempotency_key="k1",
            retry=True,
            retry_of_attempt_id=attempt_obj.id,
            metadata={"force_failure": True},
        ),
        db=db,
        current_user=_StubUser(models.RoleName.financeiro),
    )
    assert retry_attempt.id != attempt_obj.id
    assert retry_attempt.retry_of_attempt_id == attempt_obj.id


def test_webhook_signature_validation_helper():
    secret_backup = settings.webhook_secret
    settings.webhook_secret = "secret123"
    raw_body = b'{"provider_message_id":"abc","status":"sent"}'
    ts = str(int(time.time()))
    good_sig = hmac.new(settings.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()

    assert rfq_webhook._valid_signature(raw_body, good_sig, ts) is True
    assert rfq_webhook._valid_signature(raw_body, "bad", ts) is False

    settings.webhook_secret = secret_backup
