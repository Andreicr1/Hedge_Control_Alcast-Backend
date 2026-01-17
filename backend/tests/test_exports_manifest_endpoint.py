import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def _make_client_and_sessionmaker(role: models.RoleName):
    app.dependency_overrides = {}

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
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
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(role)

    return TestClient(app), TestingSessionLocal


def test_exports_manifest_is_deterministic_for_same_inputs():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    r1 = client.get("/api/exports/manifest",
        params={"export_type": "state", "subject_type": "rfq", "subject_id": 123},
        headers={"X-Request-ID": "11111111-1111-1111-1111-111111111111"},
    )
    assert r1.status_code == 200
    m1 = r1.json()

    r2 = client.get("/api/exports/manifest",
        params={"export_type": "state", "subject_type": "rfq", "subject_id": 123},
        headers={"X-Request-ID": "22222222-2222-2222-2222-222222222222"},
    )
    assert r2.status_code == 200
    m2 = r2.json()

    assert m1["export_id"] == m2["export_id"]
    assert m1["inputs_hash"] == m2["inputs_hash"]
    assert m1["filters"] == m2["filters"]


def test_exports_manifest_denies_non_authorized_roles():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.vendas)

    r = client.get("/api/exports/manifest", params={"export_type": "state"})
    assert r.status_code == 403


def test_exports_manifest_allows_auditoria_via_get_and_writes_audit_log():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.auditoria)

    r = client.get("/api/exports/manifest", params={"export_type": "state"})
    assert r.status_code == 200

    db = SessionLocal()
    try:
        logs = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "exports.manifest.requested")
            .all()
        )
        assert len(logs) == 1
    finally:
        db.close()
