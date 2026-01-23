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


def test_exports_pnl_aggregate_csv_is_downloadable_and_deterministic(_temp_storage_dir):
    client, SessionLocal, _role = _make_env(models.RoleName.financeiro)

    seed_time = datetime(2026, 1, 1, 0, 0, 0)

    with SessionLocal() as db:
        deal = models.Deal(
            commodity="AL",
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
            created_at=seed_time,
        )
        db.add(deal)
        db.flush()

        db.add(
            models.DealPNLSnapshot(
                deal_id=deal.id,
                timestamp=seed_time,
                physical_revenue=100.0,
                physical_cost=40.0,
                hedge_pnl_realized=5.0,
                hedge_pnl_mtm=2.5,
                net_pnl=67.5,
            )
        )
        db.commit()

    r = client.post("/api/exports",
        json={
            "export_type": "pnl_aggregate",
            "as_of": seed_time.isoformat(),
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
    assert len(rows) == 1

    row = rows[0]
    assert row["deal_id"] == "1"
    assert row["currency"] == "USD"
    assert row["has_snapshot"] == "true"
    assert row["net_pnl"] == "67.5"


def test_exports_pnl_aggregate_denies_vendas(_temp_storage_dir):
    client, _SessionLocal, _role = _make_env(models.RoleName.comercial)

    r = client.post("/api/exports",
        json={
            "export_type": "pnl_aggregate",
            "as_of": datetime(2026, 1, 1, 0, 0, 0).isoformat(),
        },
    )
    assert r.status_code == 403
