# ruff: noqa: E402

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.database import Base
from app.main import app
from app.models.domain import RoleName

engine = create_engine(
    os.environ["DATABASE_URL"], connect_args={"check_same_thread": False}, future=True
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


def _stub_user(role_name: RoleName):
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


client = TestClient(app)


def test_timeline_create_and_list_for_subject():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    create = client.post(
        "/api/timeline/events",
        json={
            "event_type": "SO_CREATED",
            "subject_type": "rfq",
            "subject_id": 123,
            "visibility": "all",
            "payload": {"text": "hello"},
        },
        headers={"X-Request-ID": "req-tl-1"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["subject_type"] == "rfq"
    assert body["subject_id"] == 123
    assert body["event_type"] == "SO_CREATED"

    lst = client.get("/api/timeline", params={"subject_type": "rfq", "subject_id": 123})
    assert lst.status_code == 200
    items = lst.json()
    assert len(items) >= 1
    assert any(i["id"] == body["id"] for i in items)


def test_timeline_visibility_filters_non_finance():
    # Create one finance-only and one all-visible event.
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r1 = client.post(
        "/api/timeline/events",
        json={
            "event_type": "EXPOSURE_UPDATED",
            "subject_type": "deal",
            "subject_id": 999,
            "visibility": "finance",
            "payload": {"k": "v"},
        },
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/timeline/events",
        json={
            "event_type": "EXPOSURE_UPDATED",
            "subject_type": "deal",
            "subject_id": 999,
            "visibility": "all",
            "payload": {"k": "v2"},
        },
    )
    assert r2.status_code == 201

    # Non-finance role should only see 'all'.
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.comercial)
    lst = client.get("/api/timeline", params={"subject_type": "deal", "subject_id": 999})
    assert lst.status_code == 200
    items = lst.json()
    assert all(i["visibility"] == "all" for i in items)

    # Finance role should see both.
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    lst2 = client.get("/api/timeline", params={"subject_type": "deal", "subject_id": 999})
    assert lst2.status_code == 200
    vis = {i["visibility"] for i in lst2.json()}
    assert "all" in vis
    assert "finance" in vis


def test_auditoria_global_readonly_blocks_timeline_post():
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(
        RoleName.auditoria
    )

    r = client.post(
        "/api/timeline/events",
        json={
            "event_type": "SO_CREATED",
            "subject_type": "rfq",
            "subject_id": 123,
            "visibility": "all",
            "payload": {"text": "blocked"},
        },
    )
    assert r.status_code == 403


def test_timeline_rejects_unknown_event_type():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r = client.post(
        "/api/timeline/events",
        json={
            "event_type": "UNKNOWN_TYPE",
            "subject_type": "so",
            "subject_id": 1,
            "visibility": "all",
            "payload": {"k": "v"},
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body.get("detail", {}).get("code") == "timeline.invalid_event_type"
