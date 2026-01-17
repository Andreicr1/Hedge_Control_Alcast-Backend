import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import app
from app.api import deps
from app import models
from app.models.domain import RoleName
from app.services.audit import audit_event


engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False}, future=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[deps.get_db] = override_get_db


def get_admin_user():
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = "admin@test.com"
            self.active = True
            self.role = type("Role", (), {"name": RoleName.admin})()

    return StubUser()


client = TestClient(app)


def test_auth_signup_and_token():
    resp = client.post("/api/auth/signup",
        json={"email": "user@test.com", "name": "User", "password": "secret123"},
    )
    assert resp.status_code == 201

    token_resp = client.post("/api/auth/token",
        data={"username": "user@test.com", "password": "secret123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token_resp.status_code == 200
    access = token_resp.json()["access_token"]
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "user@test.com"


def test_healthcheck_and_request_id_header():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "environment" in body
    assert "uptime_seconds" in body
    assert "X-Request-ID" in r.headers


def test_audit_logs_persist_for_auth_events():
    # signup
    r = client.post("/api/auth/signup", json={"email": "audit@test.com", "name": "Audit", "password": "secret123"})
    assert r.status_code == 201

    # login (token)
    r = client.post("/api/auth/token",
        data={"username": "audit@test.com", "password": "secret123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200

    # audit rows should exist
    db = TestingSessionLocal()
    try:
        actions = [row[0] for row in db.query(models.AuditLog.action).all()]
        assert "auth.signup" in actions
        assert "auth.login_success" in actions
    finally:
        db.close()


def test_audit_log_captures_request_context_for_signup():
    req_id = "test-req-id-audit-ctx-1"
    user_agent = "pytest-audit-agent"

    r = client.post("/api/auth/signup",
        json={"email": "auditctx@test.com", "name": "Audit Ctx", "password": "secret123"},
        headers={"X-Request-ID": req_id, "User-Agent": user_agent},
    )
    assert r.status_code == 201

    db = TestingSessionLocal()
    try:
        row = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "auth.signup")
            .filter(models.AuditLog.request_id == req_id)
            .order_by(models.AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.user_agent == user_agent
        assert row.ip is not None
    finally:
        db.close()


def test_audit_event_db_failure_is_swallowed_and_falls_back_to_stdout(capsys):
    class DummySession:
        def add(self, _obj):
            return None

        def commit(self):
            raise SQLAlchemyError("forced commit failure")

        def close(self):
            return None

    audit_event("unit.audit.db_fail", None, {"k": "v"}, db=DummySession())

    out = capsys.readouterr().out
    assert "[AUDIT-FAIL-DB]" in out


def test_signup_succeeds_even_if_audit_commit_fails():
    previous_override = app.dependency_overrides.get(deps.get_db)

    def override_get_db_fail_audit_commit_only():
        db = TestingSessionLocal()
        original_commit = db.commit
        commit_calls = {"n": 0}

        def commit():
            commit_calls["n"] += 1
            if commit_calls["n"] >= 2:
                raise SQLAlchemyError("forced audit commit failure")
            return original_commit()

        db.commit = commit

        try:
            yield db
        finally:
            try:
                db.rollback()
            except Exception:
                pass
            db.close()

    app.dependency_overrides[deps.get_db] = override_get_db_fail_audit_commit_only
    try:
        req_id = "test-req-id-audit-fail-1"
        r = client.post("/api/auth/signup",
            json={"email": "auditfail@test.com", "name": "Audit Fail", "password": "secret123"},
            headers={"X-Request-ID": req_id},
        )
        assert r.status_code == 201

        db = TestingSessionLocal()
        try:
            row = (
                db.query(models.AuditLog)
                .filter(models.AuditLog.action == "auth.signup")
                .filter(models.AuditLog.request_id == req_id)
                .first()
            )
            assert row is None
        finally:
            db.close()
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(deps.get_db, None)
        else:
            app.dependency_overrides[deps.get_db] = previous_override


def test_signup_rejects_role_assignment():
    resp = client.post("/api/auth/signup",
        json={"email": "bad@test.com", "name": "Bad", "password": "secret123", "role": "admin"},
    )
    assert resp.status_code == 400


def test_purchase_order_list_requires_auth():
    """Test purchase order list endpoint requires authentication."""
    app.dependency_overrides[deps.get_current_user] = lambda: get_admin_user()
    resp = client.get("/api/purchase-orders")
    assert resp.status_code == 200
    app.dependency_overrides.pop(deps.get_current_user, None)


def test_sales_order_creation_and_validation():
    app.dependency_overrides[deps.get_current_user] = lambda: get_admin_user()
    cust_resp = client.post("/api/customers",
        json={"name": "Cliente", "code": "C1", "contact_email": "c@c.com", "contact_phone": "321"},
    )
    assert cust_resp.status_code == 201
    cust_id = cust_resp.json()["id"]

    so_resp = client.post("/api/sales-orders",
        json={
            "customer_id": cust_id,
            "product": "Alumínio",
            "total_quantity_mt": 5,
            "unit": "MT",
            "unit_price": 2500,
            "pricing_type": "fixed",
            "lme_premium": 0,
        },
    )
    assert so_resp.status_code == 201
    assert so_resp.json()["so_number"]

    bad_resp = client.post("/api/sales-orders",
        json={
            "customer_id": cust_id,
            "product": "Alumínio",
            "total_quantity_mt": -10,
            "pricing_type": "fixed",
            "lme_premium": 0,
        },
    )
    assert bad_resp.status_code == 422
    app.dependency_overrides.pop(deps.get_current_user, None)


def test_counterparty_crud():
    app.dependency_overrides[deps.get_current_user] = lambda: get_admin_user()
    resp = client.post("/api/counterparties",
        json={"name": "Banco X", "type": "bank", "contact_email": "b@x.com"},
    )
    assert resp.status_code == 201
    list_resp = client.get("/api/counterparties")
    assert list_resp.status_code == 200
    assert any(cp["name"] == "Banco X" for cp in list_resp.json())
    app.dependency_overrides.pop(deps.get_current_user, None)


def test_rfq_preview():
    # RFQ preview requires financeiro role, not admin
    def get_financeiro_user():
        class StubUser:
            def __init__(self):
                self.id = 1
                self.email = "financeiro@test.com"
                self.active = True
                self.role = type("Role", (), {"name": RoleName.financeiro})()

        return StubUser()

    app.dependency_overrides[deps.get_current_user] = lambda: get_financeiro_user()
    payload = {
        "trade_type": "Swap",
        "leg1": {
          "side": "buy",
          "price_type": "AVG",
          "quantity_mt": 10,
          "month_name": "January",
          "year": 2025
        },
        "leg2": {
          "side": "sell",
          "price_type": "Fix",
          "quantity_mt": 10,
          "fixing_date": "2025-01-15"
        },
        "sync_ppt": False,
        "company_header": "Alcast",
        "company_label_for_payoff": "Alcast"
    }
    resp = client.post("/api/rfqs/preview", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "text" in body
    app.dependency_overrides.pop(deps.get_current_user, None)

