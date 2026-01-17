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


def _make_env(initial_role: models.RoleName = models.RoleName.financeiro):
    # Isolate from other test modules that mutate app.dependency_overrides.
    app.dependency_overrides = {}

    role_holder: list[models.RoleName] = [initial_role]

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

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(role_holder[0])
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(role_holder[0])

    return TestClient(app), TestingSessionLocal, role_holder


def test_exports_job_create_is_deterministic_and_persists_single_row():
    client, SessionLocal, _role = _make_env(models.RoleName.financeiro)

    payload = {
        "export_type": "state",
        "subject_type": "rfq",
        "subject_id": 123,
    }

    r1 = client.post("/api/exports", json=payload)
    assert r1.status_code == 201
    body1 = r1.json()
    assert body1["export_id"].startswith("exp_")
    assert len(body1["inputs_hash"]) == 64
    assert body1["status"] == "queued"
    assert body1["filters"] == {"subject_type": "rfq", "subject_id": 123}

    r2 = client.post("/api/exports", json=payload)
    assert r2.status_code == 201
    body2 = r2.json()

    assert body1["export_id"] == body2["export_id"]
    assert body1["id"] == body2["id"]

    with SessionLocal() as db:
        assert db.query(models.ExportJob).count() == 1
        assert (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "exports.job.requested")
            .count()
            == 2
        )


def test_exports_job_status_allows_auditoria_read():
    client, SessionLocal, role_holder = _make_env(models.RoleName.financeiro)

    r = client.post("/api/exports",
        json={
            "export_type": "state",
            "subject_type": "rfq",
            "subject_id": 123,
        },
    )
    assert r.status_code == 201
    export_id = r.json()["export_id"]

    r1 = client.get(f"/api/exports/{export_id}")
    assert r1.status_code == 200
    assert r1.json()["export_id"] == export_id

    role_holder[0] = models.RoleName.auditoria
    r2 = client.get(f"/api/exports/{export_id}")
    assert r2.status_code == 200
    assert r2.json()["export_id"] == export_id

    with SessionLocal() as db:
        assert (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "exports.job.status_viewed")
            .count()
            == 2
        )


def test_exports_job_create_denies_vendas():
    client, _SessionLocal, _role = _make_env(models.RoleName.vendas)

    r = client.post("/api/exports",
        json={
            "export_type": "state",
            "subject_type": "rfq",
            "subject_id": 123,
        },
    )
    assert r.status_code == 403


def test_exports_job_create_denies_auditoria():
    client, _SessionLocal, _role = _make_env(models.RoleName.auditoria)

    r = client.post("/api/exports",
        json={
            "export_type": "state",
            "subject_type": "rfq",
            "subject_id": 123,
        },
    )
    assert r.status_code == 403
