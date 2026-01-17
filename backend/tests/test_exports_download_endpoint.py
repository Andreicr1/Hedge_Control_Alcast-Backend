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


def test_exports_download_denies_when_not_done_and_never_returns_artifacts_in_status():
    client, SessionLocal, _role = _make_env(models.RoleName.financeiro)

    r = client.post("/api/exports",
        json={
            "export_type": "state",
            "subject_type": "rfq",
            "subject_id": 123,
        },
    )
    assert r.status_code == 201
    export_id = r.json()["export_id"]

    # Even if artifacts are (incorrectly) present in DB while queued, API must not expose them.
    with SessionLocal() as db:
        job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
        assert job is not None
        job.artifacts = [{"storage_uri": "https://example.com/should-not-leak"}]
        db.commit()

    status = client.get(f"/api/exports/{export_id}")
    assert status.status_code == 200
    # Rule: artifacts/links are only meaningful when status=done.
    assert status.json().get("artifacts") in (None, [])

    dl = client.get(f"/api/exports/{export_id}/download", follow_redirects=False)
    assert dl.status_code == 409


def test_exports_download_redirects_only_when_done():
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

    with SessionLocal() as db:
        job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
        assert job is not None
        job.status = "done"
        job.artifacts = [
            {
                "kind": "csv",
                "storage_uri": "https://example.com/export.csv",
                "sha256": "abc",
            }
        ]
        db.commit()

    dl = client.get(f"/api/exports/{export_id}/download", follow_redirects=False)
    assert dl.status_code in (302, 307)
    assert dl.headers["location"] == "https://example.com/export.csv"

    role_holder[0] = models.RoleName.auditoria
    dl2 = client.get(f"/api/exports/{export_id}/download", follow_redirects=False)
    assert dl2.status_code in (302, 307)

    role_holder[0] = models.RoleName.vendas
    denied = client.get(f"/api/exports/{export_id}/download", follow_redirects=False)
    assert denied.status_code == 403

    with SessionLocal() as db:
        assert (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "exports.job.download_requested")
            .count()
            == 2
        )
