"""seed base roles

Revision ID: 20231221_0002
Revises: 20231221_0001
Create Date: 2023-12-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20231221_0002_seed_roles"
down_revision = "20231221_0001_init_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.Enum(name="rolename")),
        sa.column("description", sa.String()),
    )
    op.bulk_insert(
        roles_table,
        [
            {"id": 1, "name": "admin", "description": "Administrador do sistema"},
            {"id": 2, "name": "compras", "description": "Perfil de Compras (PO)"},
            {"id": 3, "name": "vendas", "description": "Perfil de Vendas (SO)"},
            {"id": 4, "name": "financeiro", "description": "Perfil Financeiro (hedge/RFQ/MTM)"},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name IN ('admin','compras','vendas','financeiro')")
