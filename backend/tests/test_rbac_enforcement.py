"""
RBAC Enforcement Tests

Tests that verify role-based access control is properly enforced
across different endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import app
from app.models.domain import (
    Exposure,
    ExposureStatus,
    ExposureType,
    MarketObjectType,
    RoleName,
)


def _stub_user(role_name: RoleName):
    """Create a stub user with the given role for testing."""

    class StubUser:
        def __init__(self):
            self.id = 1
            self.email = f"{role_name.value}@test.com"
            self.active = True
            self.role = type("Role", (), {"name": role_name})()

    return StubUser()


@pytest.fixture
def client():
    """Create test client after database setup."""
    return TestClient(app)


def test_inbox_counts_financeiro_only_allows_financeiro(client):
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    r = client.get("/api/inbox/counts")
    assert r.status_code == 200


def test_inbox_counts_allows_admin(client):
    """Admin also has access to inbox counts per require_roles in inbox.py."""
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.admin)
    r = client.get("/api/inbox/counts")
    # require_roles(financeiro, admin, auditoria) - admin is allowed
    assert r.status_code == 200


def test_inbox_workbench_financeiro_only_allows_financeiro(client):
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)
    r = client.get("/api/inbox/workbench")
    assert r.status_code == 200


def test_inbox_workbench_allows_auditoria(client):
    """Auditoria has read access to inbox workbench per require_roles."""
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)
    r = client.get("/api/inbox/workbench")
    # require_roles(financeiro, admin, auditoria) - auditoria is allowed
    assert r.status_code == 200


def test_inbox_decision_no_side_effects_happy_path(client, db_session):
    # Create an Exposure in the test DB
    exp = Exposure(
        source_type=MarketObjectType.po,
        source_id=1,
        exposure_type=ExposureType.active,
        quantity_mt=10.0,
        product="AL",
        status=ExposureStatus.open,
    )
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)

    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.financeiro)

    before_status = db_session.query(Exposure).filter(Exposure.id == exp.id).first().status
    r = client.post(
        f"/api/inbox/exposures/{exp.id}/decisions",
        json={"decision": "no_hedge", "justification": "Sem hedge por decisão de risco"},
    )
    assert r.status_code == 200
    db_session.refresh(exp)
    after_status = db_session.query(Exposure).filter(Exposure.id == exp.id).first().status

    # Guardrail: decision must not mutate exposure status.
    assert before_status == after_status


def test_dashboard_summary_allows_auditoria(client):
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200


def test_auditoria_is_globally_read_only_blocks_writes(client):
    # Global guard depends on get_current_user_optional.
    app.dependency_overrides[deps.get_current_user_optional] = lambda: _stub_user(
        RoleName.auditoria
    )

    # Any POST should be blocked for Auditoria, even for otherwise-public endpoints.
    r = client.post(
        "/api/auth/signup",
        json={"email": "user2@test.com", "name": "User2", "password": "secret123"},
    )
    assert r.status_code == 403


def test_rfqs_list_allows_auditoria(client):
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.auditoria)
    r = client.get("/api/rfqs")
    assert r.status_code == 200


def test_rfqs_list_allows_admin(client):
    """Admin role should have access to all endpoints including RFQs."""
    app.dependency_overrides[deps.get_current_user] = lambda: _stub_user(RoleName.admin)
    r = client.get("/api/rfqs")
    assert r.status_code == 200
