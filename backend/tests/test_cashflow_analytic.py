import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import deps
from app.database import Base
from app.main import app
from app.models.domain import RoleName


engine = create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
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


def _stub_user(role_name: RoleName):
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


client = TestClient(app)


def _seed_orders_and_market_data():
    db = TestingSessionLocal()
    try:
        deal = models.Deal(
            commodity="AL",
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
        )
        customer = models.Customer(name="CF Cust")
        supplier = models.Supplier(name="CF Supp")
        db.add_all([deal, customer, supplier])
        db.flush()

        so_fix = models.SalesOrder(
            so_number="SO-FIX-1",
            deal_id=deal.id,
            customer_id=customer.id,
            product="AL",
            total_quantity_mt=10.0,
            unit_price=200.0,
            pricing_type=models.PriceType.FIX,
            expected_delivery_date=datetime.fromisoformat("2025-02-01").date(),
            status=models.OrderStatus.draft,
        )
        so_avg = models.SalesOrder(
            so_number="SO-AVG-1",
            deal_id=deal.id,
            customer_id=customer.id,
            product="AL",
            total_quantity_mt=5.0,
            pricing_type=models.PriceType.AVG,
            reference_price="Q7Y00",
            expected_delivery_date=datetime.fromisoformat("2025-02-02").date(),
            status=models.OrderStatus.active,
        )
        po_c2r = models.PurchaseOrder(
            po_number="PO-C2R-1",
            deal_id=deal.id,
            supplier_id=supplier.id,
            product="AL",
            total_quantity_mt=7.0,
            pricing_type=models.PriceType.C2R,
            reference_price="Q7Y00",
            expected_delivery_date=datetime.fromisoformat("2025-02-03").date(),
            status=models.OrderStatus.draft,
        )
        db.add_all([so_fix, so_avg, po_c2r])
        db.flush()

        # Seed MTM(D-1) market data used for variable cashflow projection.
        # as_of=2025-01-15 => D-1=2025-01-14
        db.add(
            models.LMEPrice(
                symbol="Q7Y00",
                name="Aluminum (official)",
                market="LME",
                price=100.0,
                price_type="official",
                ts_price=datetime(2025, 1, 14, 12, 0, 0, tzinfo=timezone.utc),
                source="test",
            )
        )

        # Seed an open exposure gap for the AVG SO.
        exp = models.Exposure(
            source_type=models.MarketObjectType.so,
            source_id=int(so_avg.id),
            exposure_type=models.ExposureType.active,
            quantity_mt=5.0,
            product="AL",
            delivery_date=so_avg.expected_delivery_date,
            status=models.ExposureStatus.open,
        )
        db.add(exp)

        db.commit()
    finally:
        db.close()


def test_cashflow_analytic_requires_financeiro_or_auditoria():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.comercial)
    r = client.get("/api/cashflow/analytic")
    assert r.status_code == 403


def test_cashflow_analytic_respects_fix_vs_variable_and_exposure_gap():
    _seed_orders_and_market_data()
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r = client.get("/api/cashflow/analytic", params={"as_of": "2025-01-15"})
    assert r.status_code == 200
    lines = r.json()
    assert isinstance(lines, list)

    so_fix = next(x for x in lines if x["entity_type"] == "so" and x["source_reference"] == "SO-FIX-1")
    assert so_fix["valuation_method"] == "fixed"
    assert so_fix["confidence"] == "deterministic"
    assert so_fix["direction"] == "inflow"
    assert so_fix["amount"] == 2000.0

    so_avg = next(x for x in lines if x["entity_type"] == "so" and x["source_reference"] == "SO-AVG-1")
    assert so_avg["valuation_method"] == "mtm"
    assert so_avg["confidence"] == "estimated"
    assert so_avg["valuation_reference_date"] == "2025-01-14"
    assert so_avg["unit_price_used"] == 100.0
    assert so_avg["amount"] == 500.0

    po_c2r = next(x for x in lines if x["entity_type"] == "po" and x["source_reference"] == "PO-C2R-1")
    assert po_c2r["valuation_method"] == "mtm"
    assert po_c2r["confidence"] == "estimated"
    assert po_c2r["direction"] == "outflow"
    assert po_c2r["amount"] == 700.0

    risk = next(x for x in lines if x["entity_type"] == "exposure")
    assert risk["cashflow_type"] == "risk"
    assert risk["confidence"] == "risk"
    assert risk["valuation_method"] == "mtm"
    assert risk["valuation_reference_date"] == "2025-01-14"
    assert risk["quantity_mt"] == 5.0
    assert risk["amount"] == 500.0


def test_cashflow_analytic_accepts_close_prices_for_cash_symbols():
    db = TestingSessionLocal()
    try:
        deal = models.Deal(
            commodity="AL",
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
        )
        customer = models.Customer(name="CF Cust 2")
        db.add_all([deal, customer])
        db.flush()

        so_avg_cash = models.SalesOrder(
            so_number="SO-AVG-CASH-1",
            deal_id=deal.id,
            customer_id=customer.id,
            product="AL",
            total_quantity_mt=3.0,
            pricing_type=models.PriceType.AVG,
            reference_price="P3Y00",
            expected_delivery_date=datetime.fromisoformat("2025-02-10").date(),
            status=models.OrderStatus.active,
        )
        db.add(so_avg_cash)
        db.flush()

        # as_of=2025-01-15 => D-1=2025-01-14
        db.add(
            models.LMEPrice(
                symbol="P3Y00",
                name="Aluminum (cash close)",
                market="LME",
                price=120.0,
                price_type="close",
                ts_price=datetime(2025, 1, 14, 18, 0, 0, tzinfo=timezone.utc),
                source="test",
            )
        )
        db.commit()
    finally:
        db.close()

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    r = client.get("/api/cashflow/analytic", params={"as_of": "2025-01-15"})
    assert r.status_code == 200
    lines = r.json()

    so = next(x for x in lines if x["entity_type"] == "so" and x["source_reference"] == "SO-AVG-CASH-1")
    assert so["valuation_method"] == "mtm"
    assert so["confidence"] == "estimated"
    assert so["valuation_reference_date"] == "2025-01-14"
    assert so["unit_price_used"] == 120.0
    assert so["amount"] == 360.0
