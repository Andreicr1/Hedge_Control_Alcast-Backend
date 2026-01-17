import csv
import io
import json
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


def test_exports_state_at_time_contains_expected_chain_and_is_deterministic(_temp_storage_dir):
    client, SessionLocal, _role = _make_env(models.RoleName.financeiro)

    seed_time = datetime(2026, 1, 1, 0, 0, 0)

    with SessionLocal() as db:
        customer = models.Customer(name="Cust 1", created_at=seed_time)
        supplier = models.Supplier(name="Supp 1", created_at=seed_time)
        deal = models.Deal(
            commodity="AL",
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
            created_at=seed_time,
        )
        db.add_all([customer, supplier, deal])
        db.flush()

        so = models.SalesOrder(
            so_number="SO-1",
            deal_id=deal.id,
            customer_id=customer.id,
            product="AL",
            total_quantity_mt=10.0,
            unit_price=1000.0,
            pricing_type=models.PricingType.monthly_average,
            status=models.OrderStatus.draft,
            created_at=seed_time,
        )
        db.add(so)
        db.flush()

        rfq = models.Rfq(
            deal_id=deal.id,
            rfq_number="RFQ-1",
            so_id=so.id,
            quantity_mt=10.0,
            period="2026-01",
            status=models.RfqStatus.pending,
            created_at=seed_time,
        )
        db.add(rfq)
        db.flush()

        contract = models.Contract(
            contract_id="contract-1",
            deal_id=deal.id,
            rfq_id=rfq.id,
            status=models.ContractStatus.active.value,
            trade_snapshot={"b": 1, "a": 2},
            settlement_date=None,
            created_at=seed_time,
        )
        db.add(contract)

        po = models.PurchaseOrder(
            po_number="PO-1",
            deal_id=deal.id,
            supplier_id=supplier.id,
            product="AL",
            total_quantity_mt=5.0,
            unit_price=900.0,
            pricing_type=models.PricingType.monthly_average,
            status=models.OrderStatus.draft,
            created_at=seed_time,
        )
        db.add(po)
        db.flush()

        db.add_all(
            [
                models.Exposure(
                    source_type=models.MarketObjectType.so,
                    source_id=so.id,
                    exposure_type=models.ExposureType.active,
                    quantity_mt=10.0,
                    product="AL",
                    status=models.ExposureStatus.open,
                    created_at=seed_time,
                ),
                models.Exposure(
                    source_type=models.MarketObjectType.po,
                    source_id=po.id,
                    exposure_type=models.ExposureType.passive,
                    quantity_mt=5.0,
                    product="AL",
                    status=models.ExposureStatus.open,
                    created_at=seed_time,
                ),
            ]
        )

        db.add(
            models.MTMSnapshot(
                object_type=models.MarketObjectType.so,
                object_id=so.id,
                product="AL",
                period="2026-01",
                price=1.0,
                quantity_mt=10.0,
                mtm_value=10.0,
                as_of_date=seed_time.date(),
                created_at=seed_time,
            )
        )

        db.add(
            models.AuditLog(
                action="unit.rfq",
                user_id=1,
                rfq_id=rfq.id,
                payload_json='{"z":1,"a":2}',
                created_at=seed_time,
            )
        )

        db.commit()

    r = client.post("/api/exports",
        json={
            "export_type": "state_at_time",
            "as_of": seed_time.isoformat(),
            "subject_type": "rfq",
            "subject_id": 1,
        },
    )
    assert r.status_code == 201
    export_id = r.json()["export_id"]

    with SessionLocal() as db:
        processed = run_once(db, worker_user_id=999)
        assert processed == export_id

        job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
        assert job is not None
        if job.status != "done":
            failed = (
                db.query(models.AuditLog)
                .filter(models.AuditLog.action == "exports.job.failed")
                .order_by(models.AuditLog.id.desc())
                .first()
            )
            details = failed.payload_json if failed is not None else None
            raise AssertionError(f"export job not done (status={job.status}) details={details}")

    dl1 = client.get(f"/api/exports/{export_id}/download")
    assert dl1.status_code == 200
    assert "text/csv" in dl1.headers.get("content-type", "")

    dl2 = client.get(f"/api/exports/{export_id}/download")
    assert dl2.status_code == 200
    assert dl1.content == dl2.content

    reader = csv.DictReader(io.StringIO(dl1.text))
    rows = list(reader)
    assert rows

    record_types = {row["record_type"] for row in rows}
    assert "sales_order" in record_types
    assert "purchase_order" in record_types
    assert "exposure" in record_types
    assert "rfq" in record_types
    assert "contract" in record_types
    assert "mtm_snapshot" in record_types
    assert "cashflow_item" in record_types
    assert "audit_log" in record_types

    audit_rows = [row for row in rows if row["record_type"] == "audit_log"]
    assert len(audit_rows) == 1
    audit_payload = json.loads(audit_rows[0]["payload_json"])
    assert audit_payload["payload_json"] == '{"a":2,"z":1}'

    with SessionLocal() as db:
        job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
        assert job is not None
        assert job.status == "done"
        assert isinstance(job.artifacts, list)
        assert job.artifacts and str(job.artifacts[0].get("storage_uri", "")).startswith("file://")


def test_exports_state_at_time_denies_vendas(_temp_storage_dir):
    client, _SessionLocal, _role = _make_env(models.RoleName.vendas)

    r = client.post("/api/exports",
        json={
            "export_type": "state_at_time",
            "as_of": datetime(2026, 1, 1, 0, 0, 0).isoformat(),
            "subject_type": "rfq",
            "subject_id": 1,
        },
    )
    assert r.status_code == 403
