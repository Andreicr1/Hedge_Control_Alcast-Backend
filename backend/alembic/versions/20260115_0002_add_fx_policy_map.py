"""add fx policy map (audit-friendly)

Revision ID: 20260115_0002_add_fx_policy_map
Revises: 20260115_0001_add_workflow_approvals
Create Date: 2026-01-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260115_0002_add_fx_policy_map"
down_revision = "20260115_0001_add_workflow_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fx_policy_map",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_key", sa.String(length=128), nullable=False),
        sa.Column("reporting_currency", sa.String(length=8), nullable=False),
        sa.Column("fx_symbol", sa.String(length=64), nullable=False),
        sa.Column("fx_source", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("policy_key", name="uq_fx_policy_map_policy_key"),
    )

    op.create_index("ix_fx_policy_map_policy_key", "fx_policy_map", ["policy_key"], unique=True)
    op.create_index(
        "ix_fx_policy_map_reporting_currency",
        "fx_policy_map",
        ["reporting_currency"],
        unique=False,
    )
    op.create_index(
        "ix_fx_policy_map_created_by_user_id",
        "fx_policy_map",
        ["created_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fx_policy_map_created_by_user_id", table_name="fx_policy_map")
    op.drop_index("ix_fx_policy_map_reporting_currency", table_name="fx_policy_map")
    op.drop_index("ix_fx_policy_map_policy_key", table_name="fx_policy_map")
    op.drop_table("fx_policy_map")
