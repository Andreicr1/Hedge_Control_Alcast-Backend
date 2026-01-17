import csv
import io
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.api import deps
from app.config import settings
from app.database import Base
from app.main import app
from app.services.exports_worker import run_once


@pytest.fixture(autouse=True)
def _restore_dependency_overrides():
    original = dict(app.dependency_overrides)
    try:
        yield
    finally:
        app.dependency_overrides = original


@pytest.fixture()
def _temp_storage_dir(tmp_path):
    prev = settings.storage_dir
    settings.storage_dir = str(tmp_path)
    try:
        yield tmp_path
    finally:
        settings.storage_dir = prev


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


def test_exports_audit_log_csv_is_downloadable_and_deterministic(_temp_storage_dir):
    client, SessionLocal, _role = _make_env(models.RoleName.financeiro)

    seed_time = datetime(2026, 1, 1, 0, 0, 0)

    with SessionLocal() as db:
        db.add(
            models.AuditLog(
                action="unit.seed",
                user_id=1,
                payload_json='{"b":1,"a":2}',
                request_id="req-1",
                ip="127.0.0.1",
                user_agent="pytest",
                created_at=seed_time,
            )
        )
        db.commit()

    r = client.post("/api/exports",
        json={
            "export_type": "audit_log",
        },
    )
    assert r.status_code == 201
    export_id = r.json()["export_id"]

    with SessionLocal() as db:
        processed = run_once(db, worker_user_id=999)
        assert processed == export_id

    dl1 = client.get(f"/api/exports/{export_id}/download")
    assert dl1.status_code == 200
    assert "text/csv" in dl1.headers.get("content-type", "")

    dl2 = client.get(f"/api/exports/{export_id}/download")
    assert dl2.status_code == 200
    assert dl1.content == dl2.content

    reader = csv.DictReader(io.StringIO(dl1.text))
    rows = list(reader)
    assert len(rows) >= 1

    seed_rows = [r for r in rows if r.get("action") == "unit.seed"]
    assert len(seed_rows) == 1
    assert seed_rows[0]["payload_json"] == '{"a":2,"b":1}'

    with SessionLocal() as db:
        job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
        assert job is not None
        assert job.status == "done"
        assert isinstance(job.artifacts, list)
        assert job.artifacts and str(job.artifacts[0].get("storage_uri", "")).startswith("file://")

        # Running worker again should not create new transitions.
        processed2 = run_once(db, worker_user_id=999)
        assert processed2 is None

        actions = [row[0] for row in db.query(models.AuditLog.action).all()]
        assert "exports.job.started" in actions
        assert "exports.job.completed" in actions


def test_exports_audit_log_download_denies_vendas(_temp_storage_dir):
    client, SessionLocal, _role = _make_env(models.RoleName.vendas)

    r = client.post("/api/exports",
        json={
            "export_type": "audit_log",
        },
    )
    assert r.status_code == 403

    # Direct status/download access is also denied by RBAC.
    with SessionLocal() as db:
        job = models.ExportJob(
            export_id="exp_denied",
            inputs_hash="0" * 64,
            export_type="audit_log",
            as_of=None,
            filters=None,
            status="done",
            requested_by_user_id=1,
            artifacts=[],
        )
        db.add(job)
        db.commit()

    denied = client.get("/api/exports/exp_denied/download")
    assert denied.status_code == 403
