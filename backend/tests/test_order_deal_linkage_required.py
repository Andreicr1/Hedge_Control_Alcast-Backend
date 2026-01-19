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


def test_sales_order_deal_id_cannot_be_cleared():
    app.dependency_overrides[deps.get_current_user] = lambda: get_admin_user()

    cust_resp = client.post(
        "/api/customers",
        json={
            "name": "Cliente",
            "code": "C-DEAL-REQ",
            "contact_email": "c@c.com",
            "contact_phone": "321",
        },
    )
    assert cust_resp.status_code == 201
    cust_id = cust_resp.json()["id"]

    so_resp = client.post(
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
    assert so_resp.status_code == 201
    so_id = so_resp.json()["id"]
    assert isinstance(so_resp.json().get("deal_id"), int)

    cleared = client.put(f"/api/sales-orders/{so_id}", json={"deal_id": None})
    assert cleared.status_code == 400

    app.dependency_overrides.pop(deps.get_current_user, None)


def test_purchase_order_deal_id_cannot_be_cleared(db_session):
    app.dependency_overrides[deps.get_current_user] = lambda: get_admin_user()

    deal = models.Deal(
        deal_uuid="deal-po-clear",
        currency="USD",
        status=models.DealStatus.open,
        lifecycle_status=models.DealLifecycleStatus.open,
    )
    supplier = models.Supplier(name="Fornecedor", code="S-DEAL-REQ")
    db_session.add_all([deal, supplier])
    db_session.commit()
    db_session.refresh(deal)
    db_session.refresh(supplier)

    po_resp = client.post(
        "/api/purchase-orders",
        json={
            "deal_id": deal.id,
            "supplier_id": supplier.id,
            "product": "Alumínio",
            "total_quantity_mt": 3,
            "pricing_type": "Fix",
            "lme_premium": 0,
        },
    )
    assert po_resp.status_code == 201
    po_id = po_resp.json()["id"]

    cleared = client.put(f"/api/purchase-orders/{po_id}", json={"deal_id": None})
    assert cleared.status_code == 400

    app.dependency_overrides.pop(deps.get_current_user, None)
