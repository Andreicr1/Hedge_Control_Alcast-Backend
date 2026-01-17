import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.database import Base
from app.main import app
from app.models.domain import RoleName, TimelineEvent

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


app.dependency_overrides[deps.get_db] = override_get_db


@pytest.fixture(autouse=True)
def _isolate_dependency_overrides():
    """Prevent cross-test contamination from other modules.

    Many tests in this repo mutate `app.dependency_overrides` without restoring.
    Keep this file resilient by forcing our DB override for the duration of each test.
    """

    original = dict(app.dependency_overrides)
    app.dependency_overrides[deps.get_db] = override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def _stub_user(role_name: RoleName):
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


client = TestClient(app)


def test_pnl_get_aggregated_allows_auditoria():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)
    r = client.get("/api/pnl", params={"as_of_date": "2026-01-01"})
    assert r.status_code == 200


def test_pnl_get_aggregated_allows_admin():
    # Admin is now allowed to access P&L aggregated
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.admin)
    r = client.get("/api/pnl", params={"as_of_date": "2026-01-01"})
    assert r.status_code == 200


def test_pnl_snapshot_post_allows_financeiro_dry_run():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    r = client.post("/api/pnl/snapshots",
        json={"as_of_date": "2026-01-01", "filters": {}, "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "dry_run"


def test_pnl_snapshot_post_blocks_auditoria_writes():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(
        RoleName.auditoria
    )

    r = client.post("/api/pnl/snapshots",
        json={"as_of_date": "2026-01-01", "filters": {}, "dry_run": False},
    )
    assert r.status_code == 403


def test_pnl_snapshot_emits_timeline_idempotent_post_commit():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    app.dependency_overrides[deps.get_current_user_optional] = lambda: None

    headers = {"X-Request-ID": "123e4567-e89b-12d3-a456-426614174000"}

    r1 = client.post("/api/pnl/snapshots",
        json={"as_of_date": "2026-01-01", "filters": {}, "dry_run": False},
        headers=headers,
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["kind"] == "materialized"
    inputs_hash = body1["inputs_hash"]

    r2 = client.post("/api/pnl/snapshots",
        json={"as_of_date": "2026-01-01", "filters": {}, "dry_run": False},
        headers=headers,
    )
    assert r2.status_code == 200

    db = TestingSessionLocal()
    try:
        events = (
            db.query(TimelineEvent)
            .filter(TimelineEvent.event_type == "PNL_SNAPSHOT_CREATED")
            .filter(TimelineEvent.idempotency_key == f"pnl_snapshot:create:{inputs_hash}")
            .all()
        )
        assert len(events) == 1
        assert events[0].correlation_id == headers["X-Request-ID"]
    finally:
        db.close()
