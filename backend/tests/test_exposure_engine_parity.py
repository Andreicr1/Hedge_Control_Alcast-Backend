# ruff: noqa: E402

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

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


def _make_client_and_sessionmaker():
    app.dependency_overrides = {}

    engine = create_engine(
        os.environ["DATABASE_URL"],
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

    class StubUser:
        def __init__(self, role_name: models.RoleName):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    # Default user for these tests: admin (can create both SO/PO)
    app.dependency_overrides[deps.get_current_user] = lambda: StubUser(models.RoleName.admin)

    return TestClient(app), TestingSessionLocal


def _seed_customer_supplier_and_deal(*, db):
    uid = uuid.uuid4().hex[:8]

    deal = models.Deal(currency="USD")
    db.add(deal)
    db.commit()
    db.refresh(deal)

    customer = models.Customer(name=f"Cliente-{uid}")
    db.add(customer)
    db.commit()
    db.refresh(customer)

    supplier = models.Supplier(name=f"Supplier-{uid}")
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    return customer, supplier, deal


def test_sales_order_fixed_does_not_create_exposure_and_net_exposure_empty():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        customer, _supplier, _deal = _seed_customer_supplier_and_deal(db=db)
        request_id = str(uuid.uuid4())

        payload = {
            "customer_id": customer.id,
            "product": "AL",
            "total_quantity_mt": 10.0,
            "pricing_type": "fixed",
            "pricing_period": None,
            "lme_premium": 0.0,
            "status": "draft",
        }

        r = client.post("/api/sales-orders", json=payload, headers={"X-Request-ID": request_id})
        assert r.status_code == 201
        so_id = int(r.json()["id"])

        exposures = (
            db.query(models.Exposure)
            .filter(models.Exposure.source_type == models.MarketObjectType.so)
            .filter(models.Exposure.source_id == so_id)
            .all()
        )
        assert len(exposures) == 0

        net = client.get("/api/net-exposure")
        assert net.status_code == 200
        assert net.json() == []
    finally:
        db.close()


def test_sales_order_switch_floating_to_fixed_closes_exposure_and_emits_timeline():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        customer, _supplier, _deal = _seed_customer_supplier_and_deal(db=db)
        request_id = str(uuid.uuid4())

        payload = {
            "customer_id": customer.id,
            "product": "AL",
            "total_quantity_mt": 10.0,
            "pricing_type": "monthly_average",
            "pricing_period": "2026-01",
            "lme_premium": 0.0,
            "status": "draft",
        }

        r = client.post("/api/sales-orders", json=payload, headers={"X-Request-ID": request_id})
        assert r.status_code == 201
        so_id = int(r.json()["id"])

        exp = (
            db.query(models.Exposure)
            .filter(models.Exposure.source_type == models.MarketObjectType.so)
            .filter(models.Exposure.source_id == so_id)
            .one()
        )
        assert exp.status != models.ExposureStatus.closed

        # Switch to fixed -> exposure must be closed, net exposure must be empty
        r2 = client.put(
            f"/api/sales-orders/{so_id}",
            json={"pricing_type": "fixed"},
            headers={"X-Request-ID": request_id},
        )
        assert r2.status_code == 200

        db.expire_all()
        exp2 = db.get(models.Exposure, exp.id)
        assert exp2 is not None
        assert exp2.status == models.ExposureStatus.closed

        closed_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "EXPOSURE_CLOSED")
            .filter(models.TimelineEvent.subject_type == "exposure")
            .filter(models.TimelineEvent.subject_id == exp.id)
            .all()
        )
        assert len(closed_events) == 1

        net = client.get("/api/net-exposure")
        assert net.status_code == 200
        assert net.json() == []
    finally:
        db.close()


def test_purchase_order_fixed_does_not_create_exposure():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        _customer, supplier, deal = _seed_customer_supplier_and_deal(db=db)
        request_id = str(uuid.uuid4())

        payload = {
            "supplier_id": supplier.id,
            "deal_id": deal.id,
            "product": "AL",
            "total_quantity_mt": 12.0,
            "pricing_type": "fixed",
            "pricing_period": None,
            "lme_premium": 0.0,
            "status": "draft",
        }

        r = client.post("/api/purchase-orders", json=payload, headers={"X-Request-ID": request_id})
        assert r.status_code == 201
        po_id = int(r.json()["id"])

        exposures = (
            db.query(models.Exposure)
            .filter(models.Exposure.source_type == models.MarketObjectType.po)
            .filter(models.Exposure.source_id == po_id)
            .all()
        )
        assert len(exposures) == 0
    finally:
        db.close()


def test_sales_order_cancelled_closes_exposure_and_cancels_tasks():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        customer, _supplier, _deal = _seed_customer_supplier_and_deal(db=db)
        request_id = str(uuid.uuid4())

        payload = {
            "customer_id": customer.id,
            "product": "AL",
            "total_quantity_mt": 10.0,
            "pricing_type": "monthly_average",
            "pricing_period": "2026-01",
            "lme_premium": 0.0,
            "status": "draft",
        }

        r = client.post("/api/sales-orders", json=payload, headers={"X-Request-ID": request_id})
        assert r.status_code == 201
        so_id = int(r.json()["id"])

        exp = (
            db.query(models.Exposure)
            .filter(models.Exposure.source_type == models.MarketObjectType.so)
            .filter(models.Exposure.source_id == so_id)
            .one()
        )
        task = (
            db.query(models.HedgeTask).filter(models.HedgeTask.exposure_id == exp.id).one()
        )
        assert task.status == models.HedgeTaskStatus.pending

        r2 = client.put(
            f"/api/sales-orders/{so_id}",
            json={"status": "cancelled"},
            headers={"X-Request-ID": request_id},
        )
        assert r2.status_code == 200

        db.expire_all()
        exp2 = db.get(models.Exposure, exp.id)
        assert exp2 is not None
        assert exp2.status == models.ExposureStatus.closed

        task2 = db.query(models.HedgeTask).filter(models.HedgeTask.id == task.id).one()
        assert task2.status == models.HedgeTaskStatus.cancelled
    finally:
        db.close()


def test_sales_order_delete_closes_exposure_and_emits_timeline():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        customer, _supplier, _deal = _seed_customer_supplier_and_deal(db=db)
        request_id = str(uuid.uuid4())

        payload = {
            "customer_id": customer.id,
            "product": "AL",
            "total_quantity_mt": 10.0,
            "pricing_type": "monthly_average",
            "pricing_period": "2026-01",
            "lme_premium": 0.0,
            "status": "draft",
        }

        r = client.post("/api/sales-orders", json=payload, headers={"X-Request-ID": request_id})
        assert r.status_code == 201
        so_id = int(r.json()["id"])

        exp = (
            db.query(models.Exposure)
            .filter(models.Exposure.source_type == models.MarketObjectType.so)
            .filter(models.Exposure.source_id == so_id)
            .one()
        )

        r_del = client.delete(f"/api/sales-orders/{so_id}", headers={"X-Request-ID": request_id})
        assert r_del.status_code == 204

        db.expire_all()
        exp2 = db.get(models.Exposure, exp.id)
        assert exp2 is not None
        assert exp2.status == models.ExposureStatus.closed

        closed_events = (
            db.query(models.TimelineEvent)
            .filter(models.TimelineEvent.event_type == "EXPOSURE_CLOSED")
            .filter(models.TimelineEvent.subject_type == "exposure")
            .filter(models.TimelineEvent.subject_id == exp.id)
            .all()
        )
        assert len(closed_events) == 1
    finally:
        db.close()


def test_sales_order_reconcile_dedupes_multiple_open_exposures():
    client, TestingSessionLocal = _make_client_and_sessionmaker()

    db = TestingSessionLocal()
    try:
        customer, _supplier, _deal = _seed_customer_supplier_and_deal(db=db)
        request_id = str(uuid.uuid4())

        payload = {
            "customer_id": customer.id,
            "product": "AL",
            "total_quantity_mt": 10.0,
            "pricing_type": "monthly_average",
            "pricing_period": "2026-01",
            "lme_premium": 0.0,
            "status": "draft",
        }

        r = client.post("/api/sales-orders", json=payload, headers={"X-Request-ID": request_id})
        assert r.status_code == 201
        so_id = int(r.json()["id"])

        exp1 = (
            db.query(models.Exposure)
            .filter(models.Exposure.source_type == models.MarketObjectType.so)
            .filter(models.Exposure.source_id == so_id)
            .one()
        )
        assert exp1.status != models.ExposureStatus.closed

        # Inject a second open exposure for the same SO (simulates earlier buggy writes).
        exp2 = models.Exposure(
            source_type=models.MarketObjectType.so,
            source_id=so_id,
            exposure_type=models.ExposureType.active,
            quantity_mt=10.0,
            product="AL",
            delivery_date=None,
            payment_date=None,
            sale_date=None,
            status=models.ExposureStatus.open,
        )
        db.add(exp2)
        db.commit()

        # Trigger reconcile via an update; it must close one of the exposures.
        r2 = client.put(
            f"/api/sales-orders/{so_id}",
            json={"notes": "reconcile-dedupe"},
            headers={"X-Request-ID": request_id},
        )
        assert r2.status_code == 200

        db.expire_all()
        open_exps = (
            db.query(models.Exposure)
            .filter(models.Exposure.source_type == models.MarketObjectType.so)
            .filter(models.Exposure.source_id == so_id)
            .filter(models.Exposure.status != models.ExposureStatus.closed)
            .all()
        )
        assert len(open_exps) == 1
    finally:
        db.close()
