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


def _make_client_and_sessionmaker(role: models.RoleName):
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

    def _stub_user(role_name: models.RoleName):
        class StubUser:
            def __init__(self):
                self.id = 1
                self.email = f"{role_name.value}@test.com"
                self.active = True
                self.role = type("Role", (), {"name": role_name})()

        return StubUser()

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(role)
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(role)

    return TestClient(app), TestingSessionLocal


def test_customers_list_supports_q_search_and_persists_fields():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.vendas)

    payload = {
        "name": "Cliente Alpha",
        "tax_id": "BR123456789",
        "contact_email": "alpha@corp.com",
        "contact_phone": "+55 11 99999-0000",
        "address_line": "Av. Paulista, 1000",
        "city": "São Paulo",
        "state": "SP",
        "country": "BR",
        "postal_code": "01310-100",
        "kyc_status": "approved",
        "credit_score": 780,
        "active": True,
    }

    r = client.post("/api/customers", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == payload["name"]
    assert created["tax_id"] == payload["tax_id"]
    assert created["contact_email"] == payload["contact_email"]
    assert created["credit_score"] == payload["credit_score"]

    # prefix search on tax_id
    r = client.get("/api/customers", params={"q": "BR123"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]

    # substring search on name
    r = client.get("/api/customers", params={"q": "Alpha"})
    assert r.status_code == 200
    assert any(it["id"] == created["id"] for it in r.json())


def test_suppliers_list_supports_q_search_and_persists_fields():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.compras)

    payload = {
        "name": "Fornecedor Beta",
        "tax_id": "BR99887766",
        "contact_email": "beta@supply.com",
        "contact_phone": "+55 21 98888-1111",
        "city": "Rio de Janeiro",
        "state": "RJ",
        "country": "BR",
        "kyc_status": "pending",
        "active": True,
    }

    r = client.post("/api/suppliers", json=payload)
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == payload["name"]
    assert created["tax_id"] == payload["tax_id"]

    r = client.get("/api/suppliers", params={"q": "BR998"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]


def test_counterparties_list_supports_q_search_and_persists_fields():
    client, _SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    payload = {
        "name": "Banco Gamma",
        "type": "bank",
        "tax_id": "BR111222333",
        "contact_name": "Contato Gamma",
        "contact_email": "gamma@bank.com",
        "contact_phone": "+55 31 97777-2222",
        "active": True,
    }

    r = client.post("/api/counterparties", json=payload, headers={"X-Request-ID": "test-req-id"})
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == payload["name"]
    assert created["tax_id"] == payload["tax_id"]
    assert created["contact_email"] == payload["contact_email"]

    r = client.get("/api/counterparties", params={"q": "BR111"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]

    r = client.get("/api/counterparties", params={"q": "Gamma"})
    assert r.status_code == 200
    assert any(it["id"] == created["id"] for it in r.json())


def test_deals_list_supports_q_search():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    with SessionLocal() as db:
        deal = models.Deal(
            commodity="Soybeans",
            currency="USD",
            reference_name="Operação Fornecedor Mexicano",
        )
        db.add(deal)
        db.commit()
        db.refresh(deal)

        deal_id = deal.id
        deal_uuid_prefix = deal.deal_uuid[:8]

    r = client.get("/api/deals", params={"q": deal_uuid_prefix})
    assert r.status_code == 200
    assert any(it["id"] == deal_id for it in r.json())

    r = client.get("/api/deals", params={"q": "Soy"})
    assert r.status_code == 200
    assert any(it["id"] == deal_id for it in r.json())

    r = client.get("/api/deals", params={"q": "Fornecedor"})
    assert r.status_code == 200
    assert any(it["id"] == deal_id for it in r.json())

    r = client.get("/api/deals", params={"q": str(deal_id)})
    assert r.status_code == 200
    assert any(it["id"] == deal_id for it in r.json())


def test_contracts_list_supports_q_search():
    client, SessionLocal = _make_client_and_sessionmaker(models.RoleName.financeiro)

    with SessionLocal() as db:
        deal = models.Deal(commodity="Corn", currency="USD")
        db.add(deal)
        db.commit()
        db.refresh(deal)

        contract = models.Contract(
            deal_id=deal.id,
            rfq_id=123,
            status="active",
            quote_group_id="QG-ABC-001",
            trade_snapshot={"instrument": "swap", "volume_mt": 10},
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)

        contract_id = contract.contract_id

    r = client.get("/api/contracts", params={"q": contract_id[:8]})
    assert r.status_code == 200
    assert any(it["contract_id"] == contract_id for it in r.json())

    r = client.get("/api/contracts", params={"q": "QG-ABC"})
    assert r.status_code == 200
    assert any(it["contract_id"] == contract_id for it in r.json())

    r = client.get("/api/contracts", params={"q": "123"})
    assert r.status_code == 200
    assert any(it["contract_id"] == contract_id for it in r.json())
