"""add counterparty kyc checks

Revision ID: 20260112_0003_add_counterparty_kyc_checks
Revises: 20260112_0002_add_auditoria_role
Create Date: 2026-01-12
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260112_0003_add_counterparty_kyc_checks"
down_revision = "20260112_0002_add_auditoria_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        ctx = op.get_context()
        with ctx.autocommit_block():
            op.execute("ALTER TYPE documentownertype ADD VALUE IF NOT EXISTS 'counterparty'")

    op.create_table(
        "kyc_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_type",
            sa.Enum("customer", "supplier", "counterparty", name="documentownertype"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("check_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_kyc_checks_owner", "owner_id"),
        sa.Index("ix_kyc_checks_owner_type", "owner_type"),
        sa.Index("ix_kyc_checks_type", "check_type"),
    )


def downgrade() -> None:
    op.drop_table("kyc_checks")
    # NOTE: We do not attempt to remove enum value from PostgreSQL.
