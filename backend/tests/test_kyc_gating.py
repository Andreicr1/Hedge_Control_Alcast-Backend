# ruff: noqa: E402

import os
import uuid
from datetime import datetime, timedelta

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


@pytest.fixture(autouse=True)
def _restore_dependency_overrides():
    original = dict(app.dependency_overrides)
    # Ensure our DB override is active for every test in this module.
    app.dependency_overrides[deps.get_db] = override_get_db
    try:
        yield
    finally:
        app.dependency_overrides = original


def _stub_user(role_name: models.RoleName):
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


client = TestClient(app)


def _seed_so_and_counterparty(
    *,
    db,
    customer_kyc_status: str | None = "approved",
    customer_sanctions_flag: bool = False,
    customer_risk_rating: str | None = None,
    counterparty_kyc_status: str | None = "approved",
    counterparty_sanctions_flag: bool = False,
    counterparty_risk_rating: str | None = None,
):
    uid = uuid.uuid4().hex[:8]
    deal = models.Deal(currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    cust = models.Customer(name=f"Cliente {uid}")
    cust.kyc_status = customer_kyc_status
    cust.sanctions_flag = customer_sanctions_flag
    cust.risk_rating = customer_risk_rating
    db.add(cust)
    db.commit()
    db.refresh(cust)

    so = models.SalesOrder(so_number=f"SO-{uid}", customer_id=cust.id, total_quantity_mt=10.0)
    so.deal_id = deal.id
    db.add(so)
    db.commit()
    db.refresh(so)

    cp = models.Counterparty(name=f"CP-{uid}", type=models.CounterpartyType.bank)
    cp.kyc_status = counterparty_kyc_status
    cp.sanctions_flag = counterparty_sanctions_flag
    cp.risk_rating = counterparty_risk_rating
    db.add(cp)
    db.commit()
    db.refresh(cp)

    return so, cp


def _seed_pass_checks(db, counterparty_id: int, *, expires_in_hours: int = 24):
    expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
    for check_type in ("credit", "sanctions", "risk_flag"):
        db.add(
            models.KycCheck(
                owner_type=models.DocumentOwnerType.counterparty,
                owner_id=counterparty_id,
                check_type=check_type,
                status="pass",
                score=700 if check_type == "credit" else None,
                details_json={"seed": True, "check_type": check_type},
                expires_at=expires_at,
            )
        )
    db.commit()


def test_rfq_create_blocks_when_customer_kyc_status_not_approved():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    db = TestingSessionLocal()
    try:
        so, cp = _seed_so_and_counterparty(db=db, customer_kyc_status="pending")

        r = client.post("/api/rfqs",
            json={
                "rfq_number": "RFQ-1",
                "so_id": so.id,
                "quantity_mt": 10.0,
                "period": "Jan/2026",
                "status": "pending",
                "invitations": [{"counterparty_id": cp.id, "counterparty_name": cp.name}],
            },
        )
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["code"] == "CUSTOMER_KYC_STATUS_NOT_APPROVED"
        assert body["detail"]["so_id"] == so.id
        assert body["detail"]["customer_id"] is not None
    finally:
        db.close()


def test_rfq_create_blocks_when_customer_sanctions_flagged():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    db = TestingSessionLocal()
    try:
        so, cp = _seed_so_and_counterparty(
            db=db,
            customer_kyc_status="approved",
            customer_sanctions_flag=True,
        )

        r = client.post("/api/rfqs",
            json={
                "rfq_number": "RFQ-2",
                "so_id": so.id,
                "quantity_mt": 10.0,
                "period": "Jan/2026",
                "status": "pending",
                "invitations": [{"counterparty_id": cp.id, "counterparty_name": cp.name}],
            },
        )
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["code"] == "CUSTOMER_SANCTIONS_FLAGGED"
        assert body["detail"]["so_id"] == so.id
        assert body["detail"]["customer_id"] is not None
    finally:
        db.close()


def test_rfq_create_allows_when_customer_kyc_approved():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    db = TestingSessionLocal()
    try:
        so, cp = _seed_so_and_counterparty(db=db, customer_kyc_status="approved")

        r = client.post("/api/rfqs",
            json={
                "rfq_number": "RFQ-3",
                "so_id": so.id,
                "quantity_mt": 10.0,
                "period": "Jan/2026",
                "status": "pending",
                "invitations": [{"counterparty_id": cp.id, "counterparty_name": cp.name}],
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["so_id"] == so.id
    finally:
        db.close()


def test_rfq_award_blocks_when_customer_kyc_not_approved():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    db = TestingSessionLocal()
    try:
        so, cp = _seed_so_and_counterparty(db=db, customer_kyc_status="pending")

        rfq = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-A1",
            so_id=so.id,
            quantity_mt=10.0,
            period="Jan/2026",
            status=models.RfqStatus.quoted,
        )
        db.add(rfq)
        db.commit()
        db.refresh(rfq)

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

        r = client.post(f"/api/rfqs/{rfq.id}/award", json={"quote_id": q.id, "motivo": "ok"})
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["code"] == "CUSTOMER_KYC_STATUS_NOT_APPROVED"
        assert body["detail"]["so_id"] == so.id
        assert body["detail"]["customer_id"] is not None
    finally:
        db.close()


def test_rfq_award_allows_when_checks_pass_and_creates_contracts():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    db = TestingSessionLocal()
    try:
        so, cp = _seed_so_and_counterparty(db=db, customer_kyc_status="approved")

        rfq = models.Rfq(
            deal_id=so.deal_id,
            rfq_number="RFQ-A2",
            so_id=so.id,
            quantity_mt=10.0,
            period="Jan/2026",
            status=models.RfqStatus.quoted,
        )
        db.add(rfq)
        db.commit()
        db.refresh(rfq)

        # Two legs (buy/sell) for same group so _group_trades succeeds.
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

        # First call: approval required (no domain side-effects)
        r = client.post(
            f"/api/rfqs/{rfq.id}/award",
            json={"quote_id": buy.id, "motivo": "Escolha"},
        )
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["code"] == "approval_required"
        wf_id = int(body["detail"]["workflow_request_id"])

        # Decide (approve) as financeiro (below threshold)
        r_dec = client.post(
            f"/api/workflows/requests/{wf_id}/decisions",
            json={"decision": "approved", "justification": "ok!"},
        )
        assert r_dec.status_code == 201

        # Retry with workflow_request_id: should execute award + create contracts
        r2 = client.post(
            f"/api/rfqs/{rfq.id}/award",
            json={"quote_id": buy.id, "motivo": "Escolha", "workflow_request_id": wf_id},
        )
        assert r2.status_code == 200

        contracts = db.query(models.Contract).filter(models.Contract.rfq_id == rfq.id).all()
        assert len(contracts) >= 1
        assert all(c.counterparty_id == cp.id for c in contracts)
    finally:
        db.close()


def test_counterparty_kyc_preflight_is_read_only_and_reports_missing_items():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    db = TestingSessionLocal()
    try:
        _so, cp = _seed_so_and_counterparty(db=db, counterparty_kyc_status="approved")

        before_checks = db.query(models.KycCheck).count()
        before_docs = db.query(models.KycDocument).count()

        r = client.get(f"/api/counterparties/{cp.id}/kyc/preflight")
        assert r.status_code == 200
        body = r.json()

        # Contract: strictly the required fields.
        assert set(body.keys()) == {
            "allowed",
            "reason_code",
            "blocked_counterparty_id",
            "missing_items",
            "expired_items",
            "ttl_info",
        }

        assert body["allowed"] is False
        assert body["reason_code"] == "KYC_CHECK_MISSING"
        assert body["blocked_counterparty_id"] == cp.id
        assert body["missing_items"] == ["credit"]
        assert body["ttl_info"] is None or isinstance(body["ttl_info"], dict)

        # Read-only: no persistence side effects.
        after_checks = db.query(models.KycCheck).count()
        after_docs = db.query(models.KycDocument).count()
        assert before_checks == after_checks
        assert before_docs == after_docs
    finally:
        db.close()


def test_counterparty_kyc_preflight_includes_ttl_info_when_allowed():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.financeiro)

    db = TestingSessionLocal()
    try:
        _so, cp = _seed_so_and_counterparty(db=db, counterparty_kyc_status="approved")
        _seed_pass_checks(db, cp.id)

        before_checks = db.query(models.KycCheck).count()
        r = client.get(f"/api/counterparties/{cp.id}/kyc/preflight")
        assert r.status_code == 200
        body = r.json()

        assert body["allowed"] is True
        assert body["reason_code"] is None
        assert body["blocked_counterparty_id"] is None
        assert body["missing_items"] == []
        assert body["expired_items"] == []
        assert isinstance(body["ttl_info"], dict)
        assert "by_check" in body["ttl_info"]
        assert set(body["ttl_info"]["by_check"].keys()) == {"credit", "sanctions", "risk_flag"}

        # Read-only
        after_checks = db.query(models.KycCheck).count()
        assert before_checks == after_checks
    finally:
        db.close()
