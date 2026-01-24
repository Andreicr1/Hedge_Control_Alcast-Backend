import csv
import hashlib
import io
import json
import zipfile
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


def test_exports_chain_export_generates_csv_pdf_and_bundle_deterministically(_temp_storage_dir):
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
            pricing_type=models.PriceType.AVG,
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
            deal_id=deal.id,
            rfq_id=rfq.id,
            counterparty_id=None,
            status=models.ContractStatus.active.value,
            trade_snapshot={"foo": "bar"},
            created_at=seed_time,
        )
        db.add(contract)
        db.flush()

        po = models.PurchaseOrder(
            po_number="PO-1",
            deal_id=deal.id,
            supplier_id=supplier.id,
            product="AL",
            total_quantity_mt=10.0,
            unit_price=900.0,
            pricing_type=models.PriceType.AVG,
            status=models.OrderStatus.draft,
            created_at=seed_time,
            lme_premium=0.0,
        )
        db.add(po)
        db.flush()

        exposure = models.Exposure(
            source_type=models.MarketObjectType.so,
            source_id=so.id,
            exposure_type=models.ExposureType.active,
            quantity_mt=10.0,
            product="AL",
            status=models.ExposureStatus.open,
            created_at=seed_time,
        )
        db.add(exposure)
        db.flush()

        hedge = models.Hedge(
            so_id=so.id,
            counterparty_id=1,
            quantity_mt=10.0,
            contract_price=1000.0,
            current_market_price=None,
            mtm_value=None,
            period="2026-01",
            status=models.HedgeStatus.active,
            created_at=seed_time,
        )
        db.add(hedge)
        db.flush()

        rfq.hedge_id = hedge.id

        he = models.HedgeExposure(
            hedge_id=hedge.id,
            exposure_id=exposure.id,
            quantity_mt=10.0,
            created_at=seed_time,
        )
        db.add(he)

        # Optional deal link
        dl = models.DealLink(
            deal_id=deal.id,
            entity_type=models.DealEntityType.so,
            entity_id=so.id,
            direction=models.DealDirection.buy,
            quantity_mt=10.0,
            allocation_type=models.DealAllocationType.auto,
            created_at=seed_time,
        )
        db.add(dl)

        # Seed MTM contract snapshot (contract-only)
        mtm_run = models.MtmContractSnapshotRun(
            as_of_date=seed_time.date(),
            scope_filters={"subject_type": "rfq", "subject_id": 1},
            inputs_hash="mtm_inputs_hash_" + ("0" * 48),
            requested_by_user_id=1,
        )
        db.add(mtm_run)
        db.flush()

        mtm = models.MtmContractSnapshot(
            run_id=mtm_run.id,
            as_of_date=seed_time.date(),
            contract_id=contract.contract_id,
            deal_id=deal.id,
            currency="USD",
            mtm_usd=123.45,
            methodology="contract_only",
            references={"source": "test"},
            inputs_hash="mtm_record_hash_" + ("0" * 49),
        )
        db.add(mtm)

        # Seed cashflow baseline
        cf_run = models.CashflowBaselineRun(
            as_of_date=seed_time.date(),
            scope_filters={"subject_type": "rfq", "subject_id": 1},
            inputs_hash="cf_inputs_hash_" + ("0" * 49),
            requested_by_user_id=1,
        )
        db.add(cf_run)
        db.flush()

        cfi = models.CashflowBaselineItem(
            run_id=cf_run.id,
            as_of_date=seed_time.date(),
            contract_id=contract.contract_id,
            deal_id=deal.id,
            rfq_id=rfq.id,
            counterparty_id=None,
            settlement_date=seed_time.date(),
            currency="USD",
            projected_value_usd=10.0,
            projected_methodology="baseline",
            projected_as_of=seed_time.date(),
            final_value_usd=None,
            final_methodology=None,
            observation_start=None,
            observation_end_used=None,
            last_published_cash_date=None,
            data_quality_flags=["test"],
            references={"source": "test"},
            inputs_hash="cf_item_hash_" + ("0" * 52),
        )
        db.add(cfi)

        # Seed a RFQ-linked audit log entry
        al = models.AuditLog(
            action="rfq.created",
            user_id=1,
            rfq_id=rfq.id,
            payload_json=json.dumps({"seed": True}, sort_keys=True),
            request_id="req_test",
            ip="127.0.0.1",
            user_agent="pytest",
            created_at=seed_time,
        )
        db.add(al)

        db.commit()

    r = client.post(
        "/api/exports",
        json={
            "export_type": "chain_export",
            "as_of": seed_time.isoformat(),
            "subject_type": "rfq",
            "subject_id": 1,
        },
    )
    assert r.status_code == 201
    export_id = r.json()["export_id"]

    # Run worker to completion
    with SessionLocal() as db:
        for _ in range(10):
            processed = run_once(db, worker_user_id=999)
            if processed is None:
                continue
            job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
            assert job is not None
            if job.status == "done":
                break
        else:
            job = db.query(models.ExportJob).filter(models.ExportJob.export_id == export_id).first()
            raise AssertionError(f"export job not done (status={getattr(job, 'status', None)})")

    status = client.get(f"/api/exports/{export_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done"
    artifacts = body.get("artifacts")
    assert isinstance(artifacts, list)
    assert {a.get("filename") for a in artifacts} >= {
        "chain_export.zip",
        "chain_export.csv",
        "chain_export.pdf",
        "manifest.json",
    }

    dl1 = client.get(f"/api/exports/{export_id}/download")
    assert dl1.status_code == 200
    assert "application/zip" in dl1.headers.get("content-type", "")

    dl2 = client.get(f"/api/exports/{export_id}/download")
    assert dl2.status_code == 200
    assert dl1.content == dl2.content

    # Validate the zip contains the expected files.
    zf = zipfile.ZipFile(io.BytesIO(dl1.content))
    names = set(zf.namelist())
    assert {"manifest.json", "chain_export.csv", "chain_export.pdf"}.issubset(names)

    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["export_id"] == export_id
    assert manifest["inputs_hash"] == body["inputs_hash"]
    assert manifest["as_of"] == seed_time.isoformat()
    assert manifest["gerado_em"] == seed_time.isoformat()
    assert "versoes" in manifest
    assert manifest["versoes"].get("export_schema_version") == 1

    csv_bytes = zf.read("chain_export.csv")
    pdf_bytes = zf.read("chain_export.pdf")
    expected_csv_sha = hashlib.sha256(csv_bytes).hexdigest()
    expected_pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()

    artifacts_by_name = {a["filename"]: a for a in manifest["artifacts"]}
    assert artifacts_by_name["chain_export.csv"]["checksum_sha256"] == expected_csv_sha
    assert artifacts_by_name["chain_export.pdf"]["checksum_sha256"] == expected_pdf_sha

    # Ensure chain_export CSV includes the extended compliance entities when present.
    decoded = csv_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    entity_types = {r.get("entity_type") for r in reader if r.get("record_type") == "entity"}
    assert "mtm_contract_snapshot" in entity_types
    assert "cashflow_baseline_item" in entity_types
    assert "audit_log" in entity_types

    pdf1 = client.get(f"/api/exports/{export_id}/download", params={"filename": "chain_export.pdf"})
    assert pdf1.status_code == 200
    assert "application/pdf" in pdf1.headers.get("content-type", "")

    pdf2 = client.get(f"/api/exports/{export_id}/download", params={"filename": "chain_export.pdf"})
    assert pdf2.status_code == 200
    assert pdf1.content == pdf2.content
