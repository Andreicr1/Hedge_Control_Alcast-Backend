from app.core.timeline_permissions import can_write_timeline
from app.models.domain import RoleName


def _stub_user(role_name: RoleName | None):
    class StubUser:
        def __init__(self):
            if role_name is None:
                self.role = None
            else:
                self.role = type("Role", (), {"name": role_name})()

    return StubUser()


def test_can_write_timeline_finance_visibility_allows_financeiro_and_admin():
    assert can_write_timeline(_stub_user(RoleName.financeiro), "finance") is True
    assert can_write_timeline(_stub_user(RoleName.admin), "finance") is True


def test_can_write_timeline_finance_visibility_denies_compras_vendas_auditoria():
    assert can_write_timeline(_stub_user(RoleName.compras), "finance") is False
    assert can_write_timeline(_stub_user(RoleName.vendas), "finance") is False
    assert can_write_timeline(_stub_user(RoleName.auditoria), "finance") is False


def test_can_write_timeline_all_visibility_allows_non_auditoria():
    assert can_write_timeline(_stub_user(RoleName.financeiro), "all") is True
    assert can_write_timeline(_stub_user(RoleName.compras), "all") is True
    assert can_write_timeline(_stub_user(RoleName.vendas), "all") is True


def test_can_write_timeline_all_visibility_denies_auditoria_and_missing_role():
    assert can_write_timeline(_stub_user(RoleName.auditoria), "all") is False
    assert can_write_timeline(_stub_user(None), "all") is False
