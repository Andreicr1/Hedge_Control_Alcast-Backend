import uuid

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


def _make_client_and_sessionmaker(role: models.RoleName = models.RoleName.financeiro):
    # Isolate from other test modules that mutate app.dependency_overrides.
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

    return TestClient(app), TestingSessionLocal


def test_timeline_list_includes_human_events_by_subject():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    db = SessionLocal()
    try:
        ev = models.TimelineEvent(
            event_type="human.comment.created",
            subject_type="rfq",
            subject_id=123,
            correlation_id=str(uuid.uuid4()),
            visibility="all",
            payload={"body": "hello", "thread_key": "rfq:123"},
            meta={"source": "test"},
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        r = client.get("/api/timeline", params={"subject_type": "rfq", "subject_id": 123})
        assert r.status_code == 200
        items = r.json()
        assert any(i["id"] == ev.id for i in items)
        assert any(i["event_type"] == "human.comment.created" for i in items)
    finally:
        db.close()
