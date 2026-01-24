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
    # This test module must be isolated from other tests that also mutate
    # app.dependency_overrides.
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


def _seed_so_counterparty_and_rfq(*, db, customer_kyc_status: str = "approved"):
    uid = uuid.uuid4().hex[:8]

    deal = models.Deal(currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    customer = models.Customer(name=f"Cliente-{uid}")
    customer.kyc_status = customer_kyc_status
    db.add(customer)
    db.commit()
    db.refresh(customer)

    so = models.SalesOrder(so_number=f"SO-{uid}", customer_id=customer.id, total_quantity_mt=10.0)
    so.deal_id = deal.id
    db.add(so)
    db.commit()
    db.refresh(so)

    cp = models.Counterparty(name=f"CP-{uid}", type=models.CounterpartyType.bank)
    db.add(cp)
    db.commit()
    db.refresh(cp)

    rfq = models.Rfq(
        rfq_number=f"RFQ-{uid}",
        so_id=so.id,
        quantity_mt=10.0,
        period="Jan/2026",
        status=models.RfqStatus.quoted,
        message_text="hello",
    )
    rfq.deal_id = deal.id
    db.add(rfq)
    db.commit()
    db.refresh(rfq)

    return so, cp, rfq


def _seed_so_and_counterparty(*, db, customer_kyc_status: str = "approved"):
    uid = uuid.uuid4().hex[:8]

    deal = models.Deal(currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    customer = models.Customer(name=f"Cliente-{uid}")
    customer.kyc_status = customer_kyc_status
    db.add(customer)
    db.commit()
    db.refresh(customer)

    so = models.SalesOrder(so_number=f"SO-{uid}", customer_id=customer.id, total_quantity_mt=10.0)
    so.deal_id = deal.id
    db.add(so)
    db.commit()
    db.refresh(so)

    cp = models.Counterparty(name=f"CP-{uid}", type=models.CounterpartyType.bank)
    db.add(cp)
    db.commit()
    db.refresh(cp)

    return so, cp


def test_kyc_gate_blocked_create_idempotency_correlation_visibility():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        so, cp, _rfq = _seed_so_counterparty_and_rfq(db=db, customer_kyc_status="pending")
        rfq_number = "RFQ-IDEMP-1"
        request_id = str(uuid.uuid4())

        payload = {
            "rfq_number": rfq_number,
            "so_id": so.id,
            "quantity_mt": 10.0,
            "period": "Jan/2026",
            "status": "pending",
            "invitations": [{"counterparty_id": cp.id, "counterparty_name": cp.name}],
        }

        r1 = client.post("/api/rfqs", json=payload, headers={"X-Request-ID": request_id})
        r2 = client.post("/api/rfqs", json=payload, headers={"X-Request-ID": request_id})
        assert r1.status_code == 409
        assert r2.status_code == 409

        idempotency_key = f"kyc_gate:block:rfq_create:{so.id}:{rfq_number}"
        events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "KYC_GATE_BLOCKED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .all()
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.subject_type == "so"
        assert ev.subject_id == so.id
        assert ev.visibility == "finance"
        assert ev.correlation_id == str(uuid.UUID(request_id))
        assert ev.payload["blocked_action"] == "rfq_create"
        assert ev.payload["so_id"] == so.id
        assert ev.payload["rfq_number"] == rfq_number
    finally:
        db.close()


def test_send_rfq_emits_expected_keys_and_shared_correlation(monkeypatch):
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        _so, _cp, rfq = _seed_so_counterparty_and_rfq(db=db, customer_kyc_status="approved")

        from app.services import rfq_sender

        class DummySendResult:
            def __init__(self):
                self.status = models.SendStatus.sent
                self.provider_message_id = "provider-1"
                self.error = None

        monkeypatch.setattr(rfq_sender, "send_rfq_message", lambda **_kwargs: DummySendResult())

        request_id = str(uuid.uuid4())
        payload = {
            "channel": "whatsapp",
            "idempotency_key": "idem-send-1",
            "max_retries": 1,
            "retry": False,
        }

        r = client.post(
            f"/api/rfqs/{rfq.id}/send", json=payload, headers={"X-Request-ID": request_id}
        )
        assert r.status_code == 202
        attempt_id = int(r.json()["id"])

        expected_corr = str(uuid.UUID(request_id))
        send_requested_key = f"rfq:{rfq.id}:send_requested:{payload['idempotency_key']}"
        attempt_created_key = f"rfq_send_attempt:{attempt_id}:created"
        state_changed_key = f"rfq:{rfq.id}:state_changed:quoted->sent"

        send_requested = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_SEND_REQUESTED")
            .filter(models.TimelineEvent.idempotency_key == send_requested_key)
            .one()
        )
        attempt_created = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_SEND_ATTEMPT_CREATED")
            .filter(models.TimelineEvent.idempotency_key == attempt_created_key)
            .one()
        )
        state_changed = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_STATE_CHANGED")
            .filter(models.TimelineEvent.idempotency_key == state_changed_key)
            .one()
        )

        assert send_requested.visibility == "finance"
        assert attempt_created.visibility == "finance"
        assert send_requested.subject_type == "rfq"
        assert attempt_created.subject_type == "rfq"
        assert send_requested.subject_id == rfq.id
        assert attempt_created.subject_id == rfq.id

        assert send_requested.correlation_id == expected_corr
        assert attempt_created.correlation_id == expected_corr
        assert state_changed.correlation_id == expected_corr

        assert state_changed.payload["rfq_id"] == rfq.id
        assert state_changed.payload["from_status"] == "quoted"
        assert state_changed.payload["to_status"] == "sent"

        # Idempotent replay should not duplicate Timeline rows.
        r2 = client.post(
            f"/api/rfqs/{rfq.id}/send", json=payload, headers={"X-Request-ID": request_id}
        )
        assert r2.status_code == 202

        state_changed_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_STATE_CHANGED")
            .filter(models.TimelineEvent.idempotency_key == state_changed_key)
            .all()
        )
        assert len(state_changed_events) == 1

        all_events = db.query(models.TimelineEvent).all()
        assert len(all_events) == 3
    finally:
        db.close()


def test_send_rfq_invalid_request_id_generates_uuid_and_is_shared(monkeypatch):
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        _so, _cp, rfq = _seed_so_counterparty_and_rfq(db=db, customer_kyc_status="approved")

        from app.services import rfq_sender

        class DummySendResult:
            def __init__(self):
                self.status = models.SendStatus.sent
                self.provider_message_id = "provider-2"
                self.error = None

        monkeypatch.setattr(rfq_sender, "send_rfq_message", lambda **_kwargs: DummySendResult())

        payload = {
            "channel": "whatsapp",
            "idempotency_key": "idem-send-2",
            "max_retries": 1,
            "retry": False,
        }

        r = client.post(
            f"/api/rfqs/{rfq.id}/send", json=payload, headers={"X-Request-ID": "not-a-uuid"}
        )
        assert r.status_code == 202
        attempt_id = int(r.json()["id"])

        send_requested_key = f"rfq:{rfq.id}:send_requested:{payload['idempotency_key']}"
        attempt_created_key = f"rfq_send_attempt:{attempt_id}:created"

        send_requested = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_SEND_REQUESTED")
            .filter(models.TimelineEvent.idempotency_key == send_requested_key)
            .one()
        )
        attempt_created = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_SEND_ATTEMPT_CREATED")
            .filter(models.TimelineEvent.idempotency_key == attempt_created_key)
            .one()
        )

        # correlation_id must be a UUID string, and shared across all emissions within the request
        uuid.UUID(send_requested.correlation_id)
        assert send_requested.correlation_id == attempt_created.correlation_id
        assert send_requested.correlation_id != "not-a-uuid"
    finally:
        db.close()


def test_rfq_created_emits_expected_key_correlation_visibility_and_is_idempotent():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        so, cp = _seed_so_and_counterparty(db=db, customer_kyc_status="approved")
        request_id = str(uuid.uuid4())
        rfq_number = f"RFQ-CREATED-{uuid.uuid4().hex[:6]}"

        payload = {
            "rfq_number": rfq_number,
            "so_id": so.id,
            "quantity_mt": 10.0,
            "period": "Jan/2026",
            "status": "pending",
            "invitations": [{"counterparty_id": cp.id, "counterparty_name": cp.name}],
        }

        r = client.post("/api/rfqs", json=payload, headers={"X-Request-ID": request_id})
        assert r.status_code == 201
        rfq_id = int(r.json()["id"])

        expected_corr = str(uuid.UUID(request_id))
        idempotency_key = f"rfq:{rfq_id}:created"

        ev = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_CREATED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .one()
        )
        assert ev.subject_type == "rfq"
        assert ev.subject_id == rfq_id
        assert ev.visibility == "finance"
        assert ev.correlation_id == expected_corr
        assert ev.payload["rfq_id"] == rfq_id
        assert ev.payload["rfq_number"] == rfq_number
        assert ev.payload["so_id"] == so.id

        # Idempotent replay (direct re-emit) must not create a second row.
        from app.services.timeline_emitters import emit_timeline_event

        replay = emit_timeline_event(
            db=db,
            event_type="RFQ_CREATED",
            subject_type="rfq",
            subject_id=rfq_id,
            correlation_id=expected_corr,
            idempotency_key=idempotency_key,
            visibility="finance",
            payload=ev.payload,
        )
        assert replay.created is False
        assert replay.event.id == ev.id

        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_CREATED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .count()
            == 1
        )
    finally:
        db.close()


def test_rfq_quote_created_emits_expected_key_correlation_visibility_and_is_idempotent():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        _so, cp, rfq = _seed_so_counterparty_and_rfq(db=db, customer_kyc_status="approved")
        request_id = str(uuid.uuid4())
        expected_corr = str(uuid.UUID(request_id))

        payload = {
            "counterparty_id": cp.id,
            "counterparty_name": cp.name,
            "quote_price": 100.0,
            "volume_mt": 10.0,
            "status": "quoted",
            "quote_group_id": "g1",
            "leg_side": "buy",
        }

        r = client.post(
            f"/api/rfqs/{rfq.id}/quotes", json=payload, headers={"X-Request-ID": request_id}
        )
        assert r.status_code == 201
        quote_id = int(r.json()["id"])

        idempotency_key = f"rfq_quote:{quote_id}:created"
        ev = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_QUOTE_CREATED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .one()
        )
        assert ev.subject_type == "rfq"
        assert ev.subject_id == rfq.id
        assert ev.visibility == "finance"
        assert ev.correlation_id == expected_corr
        assert ev.payload["rfq_id"] == rfq.id
        assert ev.payload["quote_id"] == quote_id

        from app.services.timeline_emitters import emit_timeline_event

        replay = emit_timeline_event(
            db=db,
            event_type="RFQ_QUOTE_CREATED",
            subject_type="rfq",
            subject_id=rfq.id,
            correlation_id=expected_corr,
            idempotency_key=idempotency_key,
            visibility="finance",
            payload=ev.payload,
        )
        assert replay.created is False
        assert replay.event.id == ev.id
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_QUOTE_CREATED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .count()
            == 1
        )
    finally:
        db.close()


def test_rfq_cancelled_emits_expected_key_correlation_visibility_and_is_idempotent():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        _so, _cp, rfq = _seed_so_counterparty_and_rfq(db=db, customer_kyc_status="approved")
        request_id = str(uuid.uuid4())
        expected_corr = str(uuid.UUID(request_id))

        motivo = "cancelled-by-test"
        r = client.post(
            f"/api/rfqs/{rfq.id}/cancel",
            params={"motivo": motivo},
            headers={"X-Request-ID": request_id},
        )
        assert r.status_code == 200

        idempotency_key = f"rfq:{rfq.id}:cancelled"
        ev = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_CANCELLED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .one()
        )
        assert ev.subject_type == "rfq"
        assert ev.subject_id == rfq.id
        assert ev.visibility == "finance"
        assert ev.correlation_id == expected_corr
        assert ev.payload["rfq_id"] == rfq.id
        assert ev.payload["reason"] == motivo

        from app.services.timeline_emitters import emit_timeline_event

        replay = emit_timeline_event(
            db=db,
            event_type="RFQ_CANCELLED",
            subject_type="rfq",
            subject_id=rfq.id,
            correlation_id=expected_corr,
            idempotency_key=idempotency_key,
            visibility="finance",
            payload=ev.payload,
        )
        assert replay.created is False
        assert replay.event.id == ev.id
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "RFQ_CANCELLED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .count()
            == 1
        )
    finally:
        db.close()


def test_kyc_gate_blocked_award_idempotency_correlation_visibility():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        so, cp, rfq = _seed_so_counterparty_and_rfq(db=db, customer_kyc_status="pending")
        q = models.RfqQuote(
            rfq_id=rfq.id,
            counterparty_id=cp.id,
            counterparty_name=cp.name,
            quote_price=100.0,
            volume_mt=10.0,
            status="quoted",
            quote_group_id="g1",
            leg_side="buy",
        )
        db.add(q)
        db.commit()
        db.refresh(q)

        request_id = str(uuid.uuid4())
        expected_corr = str(uuid.UUID(request_id))

        payload = {"quote_id": q.id, "motivo": "nok"}
        r1 = client.post(
            f"/api/rfqs/{rfq.id}/award", json=payload, headers={"X-Request-ID": request_id}
        )
        r2 = client.post(
            f"/api/rfqs/{rfq.id}/award", json=payload, headers={"X-Request-ID": request_id}
        )
        assert r1.status_code == 409
        assert r2.status_code == 409

        idempotency_key = f"kyc_gate:block:contract_create:{so.id}:{rfq.id}:{q.id}"
        events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "KYC_GATE_BLOCKED")
            .filter(models.TimelineEvent.idempotency_key == idempotency_key)
            .all()
        )
        assert len(events) == 1
        ev = events[0]
        assert ev.subject_type == "so"
        assert ev.subject_id == so.id
        assert ev.visibility == "finance"
        assert ev.correlation_id == expected_corr
        assert ev.payload["blocked_action"] == "contract_create"
        assert ev.payload["so_id"] == so.id
        assert ev.payload["rfq_id"] == rfq.id
        assert ev.payload["quote_id"] == q.id
    finally:
        db.close()


def test_contract_created_emits_per_contract_with_expected_keys_correlation_visibility_and_is_idempotent():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        _so, cp, rfq = _seed_so_counterparty_and_rfq(db=db, customer_kyc_status="approved")

        buy = models.RfqQuote(
            rfq_id=rfq.id,
            counterparty_id=cp.id,
            counterparty_name=cp.name,
            quote_price=100.0,
            volume_mt=10.0,
            status="quoted",
            quote_group_id="g1",
            leg_side="buy",
        )
        sell = models.RfqQuote(
            rfq_id=rfq.id,
            counterparty_id=cp.id,
            counterparty_name=cp.name,
            quote_price=101.0,
            volume_mt=10.0,
            status="quoted",
            quote_group_id="g1",
            leg_side="sell",
        )
        db.add(buy)
        db.add(sell)
        db.commit()
        db.refresh(buy)
        db.refresh(sell)

        request_id = str(uuid.uuid4())
        expected_corr = str(uuid.UUID(request_id))

        # First call: approval required
        r = client.post(
            f"/api/rfqs/{rfq.id}/award",
            json={"quote_id": buy.id, "motivo": "ok!"},
            headers={"X-Request-ID": request_id},
        )
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["code"] == "approval_required"
        wf_id = int(body["detail"]["workflow_request_id"])

        # Approve the workflow
        r_dec = client.post(
            f"/api/workflows/requests/{wf_id}/decisions",
            json={"decision": "approved", "justification": "test approval"},
        )
        assert r_dec.status_code == 201

        # Retry with workflow_request_id
        r2 = client.post(
            f"/api/rfqs/{rfq.id}/award",
            json={"quote_id": buy.id, "motivo": "ok!", "workflow_request_id": wf_id},
            headers={"X-Request-ID": request_id},
        )
        assert r2.status_code == 200

        contracts = db.query(models.Contract).filter(models.Contract.rfq_id == rfq.id).all()
        assert len(contracts) >= 1

        contract_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "CONTRACT_CREATED")
            .filter(models.TimelineEvent.subject_type == "rfq")
            .filter(models.TimelineEvent.subject_id == rfq.id)
            .all()
        )
        assert len(contract_events) == len(contracts)
        for c in contracts:
            key = f"contract:{c.contract_id}:created"
            ev = (
                db.query(models.TimelineEvent)
                .filter(models.TimelineEvent.event_type == "CONTRACT_CREATED")
                .filter(models.TimelineEvent.idempotency_key == key)
                .one()
            )
            assert ev.visibility == "finance"
            assert ev.correlation_id == expected_corr
            assert ev.subject_type == "rfq"
            assert ev.subject_id == rfq.id
            assert ev.payload["contract_id"] == c.contract_id
            assert ev.payload["rfq_id"] == rfq.id

        # Idempotent replay: re-emit one of the contract events directly and ensure no duplicates.
        from app.services.timeline_emitters import emit_timeline_event

        first_contract = contracts[0]
        first_key = f"contract:{first_contract.contract_id}:created"
        existing = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "CONTRACT_CREATED")
            .filter(models.TimelineEvent.idempotency_key == first_key)
            .one()
        )
        replay = emit_timeline_event(
            db=db,
            event_type="CONTRACT_CREATED",
            subject_type="rfq",
            subject_id=rfq.id,
            correlation_id=expected_corr,
            idempotency_key=first_key,
            visibility="finance",
            payload=existing.payload,
        )
        assert replay.created is False
        assert replay.event.id == existing.id
        assert (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "CONTRACT_CREATED")
            .filter(models.TimelineEvent.idempotency_key == first_key)
            .count()
            == 1
        )
    finally:
        db.close()
