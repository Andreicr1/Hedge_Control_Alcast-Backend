from fastapi.testclient import TestClient

from app import models
from app.api import deps
from app.main import app
from app.models.domain import RoleName


def get_admin_user():
    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = "admin@test.com"
            self.active = True
            self.role = type("Role", (), {"name": RoleName.admin})()

    return StubUser()


client = TestClient(app)


def test_sales_orders_list_filters_by_deal_id():
    app.dependency_overrides[deps.get_current_user] = lambda: get_admin_user()

    cust_resp = client.post(
        "/api/customers",
        json={
            "name": "Cliente",
            "code": "C-LIST",
            "contact_email": "c@c.com",
            "contact_phone": "321",
        },
    )
    assert cust_resp.status_code == 201
    cust_id = cust_resp.json()["id"]

    so1 = client.post(
        "/api/sales-orders",
        json={
            "customer_id": cust_id,
            "product": "Alumínio",
            "total_quantity_mt": 5,
            "unit": "MT",
            "unit_price": 2500,
            "pricing_type": "Fix",
            "lme_premium": 0,
        },
    )
    assert so1.status_code == 201
    deal_a = so1.json()["deal_id"]
    assert isinstance(deal_a, int)

    so2 = client.post(
        "/api/sales-orders",
        json={
            "customer_id": cust_id,
            "deal_id": deal_a,
            "product": "Alumínio",
            "total_quantity_mt": 7,
            "unit": "MT",
            "unit_price": 2550,
            "pricing_type": "Fix",
            "lme_premium": 0,
        },
    )
    assert so2.status_code == 201

    so3 = client.post(
        "/api/sales-orders",
        json={
            "customer_id": cust_id,
            "product": "Alumínio",
            "total_quantity_mt": 9,
            "unit": "MT",
            "unit_price": 2600,
            "pricing_type": "Fix",
            "lme_premium": 0,
        },
    )
    assert so3.status_code == 201
    deal_b = so3.json()["deal_id"]
    assert isinstance(deal_b, int)
    assert deal_b != deal_a

    filtered = client.get(f"/api/sales-orders?deal_id={deal_a}")
    assert filtered.status_code == 200
    rows = filtered.json()
    assert rows
    assert all(r.get("deal_id") == deal_a for r in rows)

    app.dependency_overrides.pop(deps.get_current_user, None)


def test_purchase_orders_list_filters_by_deal_id(db_session):
    app.dependency_overrides[deps.get_current_user] = lambda: get_admin_user()

    deal_a = models.Deal(
        deal_uuid="deal-list-a",
        currency="USD",
        status=models.DealStatus.open,
        lifecycle_status=models.DealLifecycleStatus.open,
    )
    deal_b = models.Deal(
        deal_uuid="deal-list-b",
        currency="USD",
        status=models.DealStatus.open,
        lifecycle_status=models.DealLifecycleStatus.open,
    )
    supplier = models.Supplier(name="Fornecedor", code="S-LIST")
    db_session.add_all([deal_a, deal_b, supplier])
    db_session.commit()
    db_session.refresh(deal_a)
    db_session.refresh(deal_b)
    db_session.refresh(supplier)

    po1 = client.post(
        "/api/purchase-orders",
        json={
            "deal_id": deal_a.id,
            "supplier_id": supplier.id,
            "product": "Alumínio",
            "total_quantity_mt": 3,
            "pricing_type": "Fix",
            "lme_premium": 0,
        },
    )
    assert po1.status_code == 201

    po2 = client.post(
        "/api/purchase-orders",
        json={
            "deal_id": deal_b.id,
            "supplier_id": supplier.id,
            "product": "Alumínio",
            "total_quantity_mt": 4,
            "pricing_type": "Fix",
            "lme_premium": 0,
        },
    )
    assert po2.status_code == 201

    filtered = client.get(f"/api/purchase-orders?deal_id={deal_a.id}")
    assert filtered.status_code == 200
    rows = filtered.json()
    assert rows
    assert all(r.get("deal_id") == deal_a.id for r in rows)

    app.dependency_overrides.pop(deps.get_current_user, None)
