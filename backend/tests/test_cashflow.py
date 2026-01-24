import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
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


def _seed_avg_contract(settlement_date_str: str):
    db = TestingSessionLocal()
    try:
        deal = models.Deal(
            commodity="AL",
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
        )
        customer = models.Customer(name="Cashflow Cust")
        db.add_all([deal, customer])
        db.flush()

        so = models.SalesOrder(
            so_number="SO-CF-1",
            deal_id=deal.id,
            customer_id=customer.id,
            product="AL",
            total_quantity_mt=10.0,
            pricing_type=models.PriceType.AVG,
            lme_premium=0.0,
            status=models.OrderStatus.draft,
        )
        db.add(so)
        db.flush()

        # Minimal RFQ + Contract compatible with contract_mtm_service AVG rules.
        rfq = models.Rfq(
            deal_id=deal.id,
            rfq_number="RFQ-CF-1",
            so_id=so.id,
            quantity_mt=10.0,
            period="Jan/2025",
            trade_specs=[
                {
                    "leg1": {"price_type": "AVG", "month_name": "January", "year": 2025},
                    "leg2": {"price_type": "FIX"},
                }
            ],
        )
        db.add(rfq)
        db.flush()

        contract = models.Contract(
            contract_id="C-CF-1",
            deal_id=deal.id,
            rfq_id=rfq.id,
            counterparty_id=1,
            status=models.ContractStatus.active.value,
            trade_index=0,
            trade_snapshot={
                "legs": [
                    {
                        "price_type": "FIX",
                        "price": 100.0,
                        "side": "buy",
                        "volume_mt": 10.0,
                    }
                ]
            },
            settlement_date=datetime.fromisoformat(settlement_date_str).date(),
        )
        db.add(contract)

        # One day of published cash settlement for Jan 1st 2025.
        db.add(
            models.LMEPrice(
                symbol="P3Y00",
                name="LME Aluminium Cash Settlement",
                market="LME",
                price=110.0,
                price_type="close",
                ts_price=datetime.fromisoformat("2025-01-01T00:00:00+00:00"),
                source="test",
            )
        )

        db.commit()
    finally:
        db.close()


def test_cashflow_requires_financeiro_or_auditoria():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.comercial)

    r = client.get("/api/cashflow")
    assert r.status_code == 403


def test_cashflow_returns_projected_values_for_financeiro():
    _seed_avg_contract("2025-01-01")

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r = client.get("/api/cashflow", params={"as_of": "2025-01-02", "limit": 50})
    assert r.status_code == 200
    body = r.json()
    assert body["as_of"] == "2025-01-02"

    items = body["items"]
    assert any(i["contract_id"] == "C-CF-1" for i in items)

    item = next(i for i in items if i["contract_id"] == "C-CF-1")
    assert item["projected_value_usd"] is not None
    assert item["projected_methodology"] == "contract.avg.realized_cash_settlement"
    assert item["projected_as_of"] == "2025-01-02"
    assert "projected_not_available" not in item["data_quality_flags"]


def test_cashflow_allows_auditoria_read_access():
    _seed_avg_contract("2025-01-01")

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)

    r = client.get("/api/cashflow", params={"as_of": "2025-01-02"})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
