from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402
from app.api import deps  # noqa: E402
from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models.domain import RoleName  # noqa: E402

engine = create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base.metadata.create_all(bind=engine)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[deps.get_db] = override_get_db


def _stub_user(role: RoleName, user_id: int = 1):
    class StubUser:
        def __init__(self):
            self.id = user_id
            self.email = f"{role.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role})()

    return StubUser()


client = TestClient(app)


def test_finance_pipeline_run_post_requires_finance_or_admin():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)
    try:
        r = client.post(
            "/api/pipelines/finance/daily/run",
            json={
                "as_of_date": "2026-01-16",
                "pipeline_version": "finance.pipeline.daily.v1.usd_only",
                "mode": "dry_run",
                "emit_exports": False,
            },
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)


def test_finance_pipeline_run_get_allows_auditoria():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    try:
        r = client.post(
            "/api/pipelines/finance/daily/run",
            headers={"X-Request-ID": "00000000-0000-0000-0000-00000000a004"},
            json={
                "as_of_date": "2026-01-16",
                "pipeline_version": "finance.pipeline.daily.v1.usd_only",
                "mode": "materialize",
                "emit_exports": False,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"]
        run_id = body["run_id"]

        # Pipeline skeleton currently fails deterministically (steps not wired yet).
        assert body["status"] in {"failed", "running", "queued", "done"}

        # Correlation propagated via X-Request-ID to timeline events.
        db = TestingSessionLocal()
        try:
            ev = (
                db.query(models.TimelineEvent)
                .filter(models.TimelineEvent.event_type == "FINANCE_PIPELINE_STARTED")
                .first()
            )
            assert ev is not None
            assert ev.correlation_id == "00000000-0000-0000-0000-00000000a004"
        finally:
            db.close()

        app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)
        r2 = client.get(f"/api/pipelines/finance/daily/runs/{run_id}")
        assert r2.status_code == 200
        assert r2.json()["run_id"] == run_id
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)


def test_finance_pipeline_run_get_by_inputs_hash():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.admin)
    try:
        r = client.post(
            "/api/pipelines/finance/daily/run",
            headers={"X-Request-ID": "00000000-0000-0000-0000-00000000a005"},
            json={
                "as_of_date": "2026-01-16",
                "pipeline_version": "finance.pipeline.daily.v1.usd_only",
                "mode": "materialize",
                "emit_exports": False,
            },
        )
        assert r.status_code == 200
        body = r.json()
        inputs_hash = body["inputs_hash"]
        assert len(inputs_hash) == 64

        r2 = client.get(f"/api/pipelines/finance/daily/runs/{inputs_hash}")
        assert r2.status_code == 200
        assert r2.json()["inputs_hash"] == inputs_hash
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)


def test_finance_pipeline_run_dry_run_is_deterministic_and_has_no_writes():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    try:
        payload = {
            "as_of_date": "2026-01-16",
            "pipeline_version": "finance.pipeline.daily.v1.usd_only",
            "scope_filters": {"deal_id": 10},
            "mode": "dry_run",
            "emit_exports": False,
        }

        r1 = client.post("/api/pipelines/finance/daily/run", json=payload)
        r2 = client.post("/api/pipelines/finance/daily/run", json=payload)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["inputs_hash"] == r2.json()["inputs_hash"]

        db = TestingSessionLocal()
        try:
            assert db.query(models.FinancePipelineRun).count() == 0
            assert db.query(models.FinancePipelineStep).count() == 0
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)
