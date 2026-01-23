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


def test_human_attachment_create_sets_thread_key_and_is_listed():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    r = client.post("/api/timeline/human/attachments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "file_id": "f-1",
            "file_name": "quote.pdf",
            "mime": "application/pdf",
            "size": 10,
            "checksum": "sha256:abc",
            "storage_uri": "s3://bucket/key",
            "visibility": "all",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["event_type"] == "human.attachment.added"
    assert body["subject_type"] == "rfq"
    assert body["subject_id"] == 123
    assert body["payload"]["thread_key"] == "rfq:123"
    assert body["payload"]["file_id"] == "f-1"

    lst = client.get("/api/timeline", params={"subject_type": "rfq", "subject_id": 123})
    assert lst.status_code == 200
    assert any(i["id"] == body["id"] for i in lst.json())


def test_human_attachment_finance_visibility_requires_financeiro_or_admin():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.comercial)

    r = client.post("/api/timeline/human/attachments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "file_id": "f-1",
            "file_name": "quote.pdf",
            "mime": "application/pdf",
            "size": 10,
            "storage_uri": "s3://bucket/key",
            "visibility": "finance",
        },
    )
    assert r.status_code == 403


def test_human_attachment_idempotency_returns_same_event():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    payload = {
        "subject_type": "rfq",
        "subject_id": 123,
        "file_id": "f-1",
        "file_name": "quote.pdf",
        "mime": "application/pdf",
        "size": 10,
        "storage_uri": "s3://bucket/key",
        "visibility": "all",
        "idempotency_key": "hc:test:attachment:1",
    }

    r1 = client.post("/api/timeline/human/attachments", json=payload)
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    r2 = client.post("/api/timeline/human/attachments", json=payload)
    assert r2.status_code == 201
    id2 = r2.json()["id"]

    assert id1 == id2


def test_human_attachment_denies_auditoria():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.auditoria)

    r = client.post("/api/timeline/human/attachments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "file_id": "f-1",
            "file_name": "quote.pdf",
            "mime": "application/pdf",
            "size": 10,
            "storage_uri": "s3://bucket/key",
            "visibility": "all",
        },
    )
    assert r.status_code == 403


def test_human_attachment_upload_then_add_event_then_download(tmp_path, monkeypatch):
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    import app.services.timeline_attachments_storage as tas

    monkeypatch.setattr(tas, "storage_root", lambda: tmp_path)

    up = client.post("/api/timeline/human/attachments/upload",
        data={"visibility": "all"},
        files={"file": ("hello.txt", b"hello", "text/plain")},
    )
    assert up.status_code == 201
    meta = up.json()
    assert meta["file_id"].startswith("file_")
    assert meta["checksum"].startswith("sha256:")

    ev = client.post("/api/timeline/human/attachments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "file_id": meta["file_id"],
            "file_name": meta["file_name"],
            "mime": meta["mime"],
            "size": meta["size"],
            "checksum": meta["checksum"],
            "storage_uri": meta["storage_uri"],
            "visibility": "all",
        },
    )
    assert ev.status_code == 201
    event_id = ev.json()["id"]

    dl = client.get(f"/api/timeline/human/attachments/{event_id}/download")
    assert dl.status_code == 200
    assert dl.content == b"hello"


def test_human_attachment_download_enforces_visibility(tmp_path, monkeypatch):
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    import app.services.timeline_attachments_storage as tas

    monkeypatch.setattr(tas, "storage_root", lambda: tmp_path)

    up = client.post("/api/timeline/human/attachments/upload",
        data={"visibility": "finance"},
        files={"file": ("secret.txt", b"secret", "text/plain")},
    )
    assert up.status_code == 201
    meta = up.json()

    ev = client.post("/api/timeline/human/attachments",
        json={
            "subject_type": "rfq",
            "subject_id": 123,
            "file_id": meta["file_id"],
            "file_name": meta["file_name"],
            "mime": meta["mime"],
            "size": meta["size"],
            "checksum": meta["checksum"],
            "storage_uri": meta["storage_uri"],
            "visibility": "finance",
        },
    )
    assert ev.status_code == 201
    event_id = ev.json()["id"]

    # Switch user to vendas, keeping the same DB.
    def _stub_user(role_name: models.RoleName):
        class StubUser:
            def __init__(self):
                self.id = 2
                self.email = f"{role_name.value}@test.com"
                self.active = True
                self.role = type("Role", (), {"name": role_name})()

        return StubUser()

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(models.RoleName.comercial)
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(
        models.RoleName.comercial
    )

    dl = client.get(f"/api/timeline/human/attachments/{event_id}/download")
    assert dl.status_code == 403
