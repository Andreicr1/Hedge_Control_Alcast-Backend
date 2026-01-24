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
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(role)

    return TestClient(app), TestingSessionLocal


def test_human_comment_create_sets_thread_key_and_is_listed():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    r = client.post(
        "/api/timeline/human/comments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "body": "hello",
            "visibility": "all",
            "mentions": ["user@test.com"],
            "attachments": [],
        },
        headers={"X-Request-ID": "2d8e9a6a-6c7e-4a3e-98f9-9e6f7fd1f16a"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["event_type"] == "human.comment.created"
    assert body["subject_type"] == "rfq"
    assert body["subject_id"] == 123
    assert body["payload"]["thread_key"] == "rfq:123"
    assert body["payload"]["body"] == "hello"

    lst = client.get("/api/timeline", params={"subject_type": "rfq", "subject_id": 123})
    assert lst.status_code == 200
    assert any(i["id"] == body["id"] for i in lst.json())


def test_human_comment_finance_visibility_requires_financeiro_or_admin():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.comercial)

    r = client.post(
        "/api/timeline/human/comments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "body": "finance-only",
            "visibility": "finance",
        },
    )
    assert r.status_code == 403


def test_human_comment_idempotency_returns_same_event():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    payload = {
        "subject_type": "rfq",
        "subject_id": 123,
        "body": "hello",
        "visibility": "all",
        "idempotency_key": "hc:test:comment:1",
    }

    r1 = client.post("/api/timeline/human/comments", json=payload)
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    r2 = client.post("/api/timeline/human/comments", json=payload)
    assert r2.status_code == 201
    id2 = r2.json()["id"]

    assert id1 == id2

    # Ensure mention events are not duplicated by repeated idempotent call.
    db = SessionLocal()
    try:
        mention_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "human.mentioned")
            .filter(models.TimelineEvent.idempotency_key.like("hc:test:comment:1:mention:%"))
            .all()
        )
        assert len(mention_events) == 0
    finally:
        db.close()


def test_human_comment_denies_auditoria():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.auditoria)

    r = client.post(
        "/api/timeline/human/comments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "body": "blocked",
            "visibility": "all",
        },
    )
    assert r.status_code == 403


def test_human_comment_mentions_are_normalized_and_emit_human_mentioned_events():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    r = client.post(
        "/api/timeline/human/comments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "body": "hello @User@Test.com",
            "visibility": "all",
            "idempotency_key": "hc:test:comment:mentions:1",
            "mentions": [" User@Test.com ", "@user@test.com", "2", "2"],
        },
    )
    assert r.status_code == 201
    comment = r.json()
    assert comment["payload"]["mentions"] == ["user@test.com", "2"]

    db = SessionLocal()
    try:
        mention_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "human.mentioned")
            .filter(
                models.TimelineEvent.idempotency_key.like("hc:test:comment:mentions:1:mention:%")
            )
            .all()
        )
        assert len(mention_events) == 2
        payloads = [e.payload for e in mention_events]
        assert all(p.get("thread_key") == "rfq:123" for p in payloads)
        assert all(p.get("comment_event_id") == comment["id"] for p in payloads)
        mentions = sorted(p.get("mention") for p in payloads)
        assert mentions == ["2", "user@test.com"]
    finally:
        db.close()

    # Second call with same idempotency must not duplicate mention events.
    r2 = client.post(
        "/api/timeline/human/comments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "body": "hello @User@Test.com",
            "visibility": "all",
            "idempotency_key": "hc:test:comment:mentions:1",
            "mentions": ["user@test.com", "2"],
        },
    )
    assert r2.status_code == 201
    assert r2.json()["id"] == comment["id"]

    db2 = SessionLocal()
    try:
        mention_events_2 = (
            db2.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "human.mentioned")
            .filter(
                models.TimelineEvent.idempotency_key.like("hc:test:comment:mentions:1:mention:%")
            )
            .all()
        )
        assert len(mention_events_2) == 2
    finally:
        db2.close()


def test_human_comment_correction_creates_superseding_event_and_is_listed():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    base = client.post(
        "/api/timeline/human/comments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "body": "original",
            "visibility": "all",
            "idempotency_key": "hc:test:comment:correction:base:1",
        },
    )
    assert base.status_code == 201
    base_event = base.json()

    corr = client.post(
        "/api/timeline/human/comments/corrections",
        json={
            "supersedes_event_id": base_event["id"],
            "body": "corrected @User@Test.com",
            "idempotency_key": "hc:test:comment:correction:1",
            "mentions": [" User@Test.com ", "@user@test.com"],
            "attachments": [],
        },
    )
    assert corr.status_code == 201
    corr_event = corr.json()

    assert corr_event["event_type"] == "human.comment.corrected"
    assert corr_event["subject_type"] == "rfq"
    assert corr_event["subject_id"] == 123
    assert corr_event["supersedes_event_id"] == base_event["id"]
    assert corr_event["visibility"] == "all"
    assert corr_event["payload"]["thread_key"] == "rfq:123"
    assert corr_event["payload"]["body"] == "corrected @User@Test.com"
    assert corr_event["payload"]["mentions"] == ["user@test.com"]

    # Both events exist in listing (append-only).
    lst = client.get("/api/timeline", params={"subject_type": "rfq", "subject_id": 123})
    assert lst.status_code == 200
    ids = {i["id"] for i in lst.json()}
    assert base_event["id"] in ids
    assert corr_event["id"] in ids

    db = SessionLocal()
    try:
        mention_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "human.mentioned")
            .filter(
                models.TimelineEvent.idempotency_key.like("hc:test:comment:correction:1:mention:%")
            )
            .all()
        )
        assert len(mention_events) == 1
        payload = mention_events[0].payload
        assert payload.get("thread_key") == "rfq:123"
        assert payload.get("mention") == "user@test.com"
        assert payload.get("comment_event_id") == corr_event["id"]
    finally:
        db.close()


def test_human_comment_correction_idempotency_returns_same_event_and_no_duplicate_mentions():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    base = client.post(
        "/api/timeline/human/comments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "body": "original",
            "visibility": "all",
        },
    )
    assert base.status_code == 201
    base_id = base.json()["id"]

    payload = {
        "supersedes_event_id": base_id,
        "body": "corrected",
        "idempotency_key": "hc:test:comment:correction:idem:1",
        "mentions": ["user@test.com", "2"],
    }

    r1 = client.post("/api/timeline/human/comments/corrections", json=payload)
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    r2 = client.post("/api/timeline/human/comments/corrections", json=payload)
    assert r2.status_code == 201
    id2 = r2.json()["id"]
    assert id1 == id2

    db = SessionLocal()
    try:
        mention_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "human.mentioned")
            .filter(
                models.TimelineEvent.idempotency_key.like(
                    "hc:test:comment:correction:idem:1:mention:%"
                )
            )
            .all()
        )
        assert len(mention_events) == 2
    finally:
        db.close()


def test_human_comment_correction_denies_auditoria():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.auditoria)

    db = SessionLocal()
    try:
        ev = models.TimelineEvent(
            event_type="human.comment.created",
            subject_type="rfq",
            subject_id=123,
            correlation_id="00000000-0000-0000-0000-000000000000",
            visibility="all",
            payload={"body": "x", "thread_key": "rfq:123", "mentions": [], "attachments": []},
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        supersedes_id = ev.id
    finally:
        db.close()

    r = client.post(
        "/api/timeline/human/comments/corrections",
        json={"supersedes_event_id": supersedes_id, "body": "blocked"},
    )
    assert r.status_code == 403


def test_human_comment_correction_finance_visibility_requires_financeiro_or_admin():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.comercial)

    db = SessionLocal()
    try:
        ev = models.TimelineEvent(
            event_type="human.comment.created",
            subject_type="rfq",
            subject_id=123,
            correlation_id="00000000-0000-0000-0000-000000000000",
            visibility="finance",
            payload={"body": "x", "thread_key": "rfq:123", "mentions": [], "attachments": []},
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        supersedes_id = ev.id
    finally:
        db.close()

    r = client.post(
        "/api/timeline/human/comments/corrections",
        json={"supersedes_event_id": supersedes_id, "body": "denied"},
    )
    assert r.status_code == 403


def test_human_comment_correction_404_when_superseded_not_found():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    r = client.post(
        "/api/timeline/human/comments/corrections",
        json={"supersedes_event_id": 999_999, "body": "nope"},
    )
    assert r.status_code == 404
