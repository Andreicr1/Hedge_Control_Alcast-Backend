"""add auditoria role

Revision ID: 20260112_0002_add_auditoria_role
Revises: 20260112_0001_add_audit_request_context
Create Date: 2026-01-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260112_0002_add_auditoria_role"
down_revision = "20260112_0001_add_audit_request_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # PostgreSQL enum value additions may require autocommit.
        ctx = op.get_context()
        with ctx.autocommit_block():
            # NOTE: Older schemas used a PostgreSQL enum type named `rolename`, but
            # later migrations migrated these columns to VARCHAR and dropped enums.
            # Only attempt to mutate the enum if it still exists.
            enum_exists = bind.execute(
                sa.text("SELECT 1 FROM pg_type WHERE typname = 'rolename' LIMIT 1")
            ).fetchone()
            if enum_exists:
                op.execute("ALTER TYPE rolename ADD VALUE IF NOT EXISTS 'auditoria'")

    # Insert only if not already present (idempotent for dev DBs).
    existing = bind.execute(sa.text("SELECT 1 FROM roles WHERE name = :name LIMIT 1"), {"name": "auditoria"}).fetchone()
    if not existing:
        # Use a high id to avoid colliding with early seed ids.
        bind.execute(
            sa.text(
                "INSERT INTO roles (id, name, description) VALUES (:id, :name, :description)"
            ),
            {"id": 10, "name": "auditoria", "description": "Perfil de Auditoria (read-only global)"},
        )


def downgrade() -> None:
    op.execute("DELETE FROM roles WHERE name = 'auditoria'")
    # NOTE: We do not attempt to remove the enum value from PostgreSQL.
