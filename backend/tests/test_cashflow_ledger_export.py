# ruff: noqa: E402, I001

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REPORTS_PUBLIC_TOKEN", "public-token-12345678")

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


def _seed_ledger_data():
    db = TestingSessionLocal()
    try:
        deal = models.Deal(
            commodity="AL",
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
        )
        customer = models.Customer(name="LED Cust")
        supplier = models.Supplier(name="LED Supp")
        db.add_all([deal, customer, supplier])
        db.flush()

        so_avg = models.SalesOrder(
            so_number="SO-LED-AVG-1",
            deal_id=deal.id,
            customer_id=customer.id,
            product="AL",
            total_quantity_mt=5.0,
            pricing_type=models.PriceType.AVG,
            reference_price="P3Y00",
            expected_delivery_date=datetime.fromisoformat("2025-02-02").date(),
            status=models.OrderStatus.active,
        )
        po_avg = models.PurchaseOrder(
            po_number="PO-LED-AVG-1",
            deal_id=deal.id,
            supplier_id=supplier.id,
            product="AL",
            total_quantity_mt=7.0,
            pricing_type=models.PriceType.AVG,
            reference_price="P3Y00",
            expected_delivery_date=datetime.fromisoformat("2025-02-03").date(),
            status=models.OrderStatus.active,
        )
        db.add_all([so_avg, po_avg])
        db.flush()

        rfq = models.Rfq(
            deal_id=deal.id,
            rfq_number="RFQ-LED-1",
            so_id=so_avg.id,
            quantity_mt=5.0,
            period="Feb/2025",
            status=models.RfqStatus.awarded,
        )
        db.add(rfq)
        db.flush()

        contract = models.Contract(
            deal_id=deal.id,
            rfq_id=rfq.id,
            status=models.ContractStatus.active.value,
            trade_snapshot={
                "legs": [
                    {"side": "buy", "price_type": "Fix", "price": 90.0, "volume_mt": 5.0},
                    {"side": "sell", "price_type": "AVG", "volume_mt": 5.0},
                ]
            },
            settlement_date=datetime.fromisoformat("2025-02-04").date(),
        )
        db.add(contract)

        # as_of=2025-01-15 => valuation_reference_date=2025-01-14
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

        db.commit()
    finally:
        db.close()


def test_cashflow_ledger_export_json_uses_last_official_for_variable_orders_and_contract_legs():
    _seed_ledger_data()
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r = client.get("/api/reports/cashflow-ledger", params={"as_of": "2025-01-15"})
    assert r.status_code == 200
    lines = r.json()
    assert isinstance(lines, list)

    so = next(
        x for x in lines if x["entity_type"] == "so" and x["source_reference"] == "SO-LED-AVG-1"
    )
    assert so["unit_price_used"] == 100.0
    assert so["lme_symbol_used"] == "Q7Y00"
    assert so["amount_usd"] == 500.0

    po = next(
        x for x in lines if x["entity_type"] == "po" and x["source_reference"] == "PO-LED-AVG-1"
    )
    assert po["unit_price_used"] == 100.0
    assert po["lme_symbol_used"] == "Q7Y00"
    assert po["amount_usd"] == -700.0

    # Contract legs are exported separately (sell positive, buy negative).
    sell_leg = next(
        x for x in lines if x["entity_type"] == "contract_leg" and x.get("side") == "sell"
    )
    buy_leg = next(
        x for x in lines if x["entity_type"] == "contract_leg" and x.get("side") == "buy"
    )

    assert sell_leg["unit_price_used"] == 100.0
    assert sell_leg["amount_usd"] == 500.0

    assert buy_leg["unit_price_used"] == 90.0
    assert buy_leg["amount_usd"] == -450.0


def test_cashflow_ledger_export_csv_returns_csv_content_type():
    _seed_ledger_data()
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r = client.get(
        "/api/reports/cashflow-ledger",
        params={"as_of": "2025-01-15", "format": "csv"},
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/csv")
    assert "entity_type" in r.text


def test_cashflow_ledger_public_accepts_bearer_token():
    _seed_ledger_data()

    r = client.get(
        "/api/reports/cashflow-ledger-public",
        params={"as_of": "2025-01-15"},
        headers={"Authorization": "Bearer public-token-12345678"},
    )
    assert r.status_code == 200
    lines = r.json()
    assert isinstance(lines, list)
    assert any(x["entity_type"] == "so" for x in lines)


def test_cashflow_ledger_public_accepts_query_token_fallback():
    _seed_ledger_data()

    r = client.get(
        "/api/reports/cashflow-ledger-public",
        params={"as_of": "2025-01-15", "token": "public-token-12345678"},
    )
    assert r.status_code == 200


def test_cashflow_ledger_public_accepts_x_reports_token_header():
    _seed_ledger_data()

    r = client.get(
        "/api/reports/cashflow-ledger-public",
        params={"as_of": "2025-01-15"},
        headers={"X-Reports-Token": "public-token-12345678"},
    )
    assert r.status_code == 200
