from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.api import deps
from app.database import Base, get_db
from app.main import app
from app.models.domain import RoleName

# Use a unique in-memory database for this test module
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_db_and_overrides():
    # Reset DB tables between tests.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Apply our override before each test (may have been changed by conftest or other tests)
    app.dependency_overrides[get_db] = override_get_db

    yield

    # Don't restore - let conftest handle cleanup


def _stub_user(role_name: RoleName):
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


client = TestClient(app)


def _seed_avg_contract_with_pnl(*, settlement_date: str = "2025-02-05") -> None:
    db = TestingSessionLocal()
    try:
        deal = models.Deal(
            commodity="AL",
            currency="USD",
            status=models.DealStatus.open,
            lifecycle_status=models.DealLifecycleStatus.open,
        )
        customer = models.Customer(name="Cashflow Adv Cust")
        db.add_all([deal, customer])
        db.flush()

        so = models.SalesOrder(
            so_number="SO-CF-ADV-1",
            deal_id=deal.id,
            customer_id=customer.id,
            product="AL",
            total_quantity_mt=10.0,
            pricing_type=models.PricingType.monthly_average,
            lme_premium=0.0,
            status=models.OrderStatus.draft,
        )
        db.add(so)
        db.flush()

        rfq = models.Rfq(
            deal_id=deal.id,
            rfq_number="RFQ-CF-ADV-1",
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
            contract_id="C-CF-ADV-1",
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
            settlement_date=datetime.fromisoformat(settlement_date).date(),
        )
        db.add(contract)

        # One published cash settlement point.
        db.add(
            models.MarketPrice(
                source="westmetall",
                symbol="ALUMINUM_CASH_SETTLEMENT",
                price=110.0,
                currency="USD",
                as_of=datetime.fromisoformat("2025-01-01T00:00:00"),
                fx=False,
            )
        )

        # Proxy 3M point (fallback method).
        db.add(
            models.MarketPrice(
                source="westmetall",
                symbol="ALUMINUM_3M_SETTLEMENT",
                price=115.0,
                currency="USD",
                as_of=datetime.fromisoformat("2025-01-01T00:00:00"),
                fx=False,
            )
        )

        run = models.PnlSnapshotRun(
            as_of_date=datetime.fromisoformat("2025-01-10T00:00:00").date(),
            scope_filters=None,
            inputs_hash="pnlhash",
            requested_by_user_id=None,
        )
        db.add(run)
        db.flush()

        db.add(
            models.PnlContractSnapshot(
                run_id=run.id,
                as_of_date=run.as_of_date,
                contract_id=contract.contract_id,
                deal_id=contract.deal_id,
                currency="USD",
                unrealized_pnl_usd=50.0,
                methodology="test",
                data_quality_flags=[],
                inputs_hash="pnlhash",
            )
        )

        db.commit()
    finally:
        db.close()


def test_preview_requires_financeiro_or_auditoria():
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.vendas)

    r = client.post("/api/cashflow/advanced/preview", json={"as_of": "2025-01-10"})
    assert r.status_code == 403


def test_preview_allows_auditoria_even_though_post_is_compute_only():
    _seed_avg_contract_with_pnl()

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)

    r = client.post(
        "/api/cashflow/advanced/preview",
        json={
            "as_of": "2025-01-10",
            "assumptions": {"forward_price_assumption": 120.0},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["inputs_hash"]
    assert body["items"]
    assert body["bucket_totals"]
    assert body["aggregates"]


def test_preview_is_deterministic_and_returns_future_pnl_impact_usd():
    _seed_avg_contract_with_pnl()

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    payload = {
        "as_of": "2025-01-10",
        "assumptions": {"forward_price_assumption": 120.0},
    }

    r1 = client.post("/api/cashflow/advanced/preview", json=payload)
    r2 = client.post("/api/cashflow/advanced/preview", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200

    b1 = r1.json()
    b2 = r2.json()
    assert b1["inputs_hash"] == b2["inputs_hash"]
    # Strong determinism check: list ordering + values must match.
    assert b1 == b2

    item = next(i for i in b1["items"] if i["contract_id"] == "C-CF-ADV-1")
    assert item["references"]
    assert isinstance(item["methodologies"], list)
    assert isinstance(item["flags"], list)

    proj0 = next(p for p in item["projections"] if p["sensitivity_pct"] == 0.0)

    # Stable ordering: scenario then sensitivity.
    scenario_order = {"base": 0, "optimistic": 1, "pessimistic": 2}
    order_keys = [
        (scenario_order.get(p["scenario"], 99), float(p["sensitivity_pct"]))
        for p in item["projections"]
    ]
    assert order_keys == sorted(order_keys)

    scenario_order = {"base": 0, "optimistic": 1, "pessimistic": 2}
    proj_keys = [(p["scenario"], float(p["sensitivity_pct"])) for p in item["projections"]]
    assert proj_keys == sorted(
        proj_keys,
        key=lambda k: (scenario_order.get(k[0], 99), k[1]),
    )

    assert proj0["expected_settlement_value_usd"] is not None
    assert proj0["pnl_current_unrealized_usd"] == 50.0
    assert proj0["future_pnl_impact_usd"] == pytest.approx(
        proj0["expected_settlement_value_usd"] - 50.0
    )

    # Aggregation bucket is settlement_date.
    assert any(a["bucket_date"] == "2025-02-05" for a in b1["aggregates"])

    # Bucket totals are explicitly materialized for frontend.
    bt = next(
        b
        for b in b1["bucket_totals"]
        if b["bucket_date"] == "2025-02-05" and b["currency"] == "USD"
    )
    assert bt["references"]
    assert isinstance(bt["methodologies"], list)
    assert isinstance(bt["flags"], list)

    bt_keys = [
        (
            b["bucket_date"],
            b["currency"],
            b["scenario"],
            float(b["sensitivity_pct"]),
        )
        for b in b1["bucket_totals"]
    ]
    assert bt_keys == sorted(
        bt_keys,
        key=lambda k: (k[0], k[1], scenario_order.get(k[2], 99), k[3]),
    )

    agg_keys = [
        (
            a["bucket_date"],
            a.get("deal_id") or 0,
            a.get("counterparty_id") or 0,
            a["currency"],
            a["scenario"],
            float(a["sensitivity_pct"]),
        )
        for a in b1["aggregates"]
    ]
    assert agg_keys == sorted(
        agg_keys,
        key=lambda k: (k[0], k[1], k[2], k[3], scenario_order.get(k[4], 99), k[5]),
    )


def test_preview_multi_currency_requires_explicit_fx():
    _seed_avg_contract_with_pnl()

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r = client.post(
        "/api/cashflow/advanced/preview",
        json={
            "as_of": "2025-01-10",
            "reporting": {"reporting_currency": "BRL"},
            "assumptions": {"forward_price_assumption": 120.0},
        },
    )
    assert r.status_code == 200
    body = r.json()

    item = next(i for i in body["items"] if i["contract_id"] == "C-CF-ADV-1")
    proj0 = next(p for p in item["projections"] if p["sensitivity_pct"] == 0.0)

    assert "fx_not_available" in proj0["flags"]
    assert proj0["expected_settlement_value_reporting"] is None
    assert proj0["pnl_current_unrealized_reporting"] is None
    assert proj0["future_pnl_impact_reporting"] is None

    # Without FX, consolidations stay in USD.
    assert any(b["currency"] == "USD" for b in body["bucket_totals"])


def test_preview_multi_currency_converts_when_fx_is_explicit():
    _seed_avg_contract_with_pnl()

    db = TestingSessionLocal()
    try:
        db.add(
            models.MarketPrice(
                source="yahoo",
                symbol="USDBRL=X",
                price=5.0,
                currency="BRL",
                as_of=datetime.fromisoformat("2025-01-09T00:00:00"),
                fx=True,
            )
        )
        db.commit()
    finally:
        db.close()

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    r = client.post(
        "/api/cashflow/advanced/preview",
        json={
            "as_of": "2025-01-10",
            "reporting": {
                "reporting_currency": "BRL",
                "fx": {"mode": "explicit", "fx_symbol": "USDBRL=X", "fx_source": "yahoo"},
            },
            "assumptions": {"forward_price_assumption": 120.0},
        },
    )
    assert r.status_code == 200
    body = r.json()

    item = next(i for i in body["items"] if i["contract_id"] == "C-CF-ADV-1")
    proj0 = next(p for p in item["projections"] if p["sensitivity_pct"] == 0.0)

    assert proj0["expected_settlement_value_usd"] is not None
    assert proj0["expected_settlement_value_reporting"] == pytest.approx(
        proj0["expected_settlement_value_usd"] * 5.0
    )
    assert proj0["pnl_current_unrealized_reporting"] == pytest.approx(50.0 * 5.0)
    assert proj0["future_pnl_impact_reporting"] == pytest.approx(
        proj0["future_pnl_impact_usd"] * 5.0
    )

    # With explicit FX, bucket totals use reporting currency.
    assert any(b["currency"] == "BRL" for b in body["bucket_totals"])
