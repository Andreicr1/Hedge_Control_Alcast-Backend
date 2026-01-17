"""add hedge exposure links

Revision ID: 20250110_0005
Revises: 20250110_0004
Create Date: 2025-01-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20250110_0005_hedge_links"
down_revision = "20250110_0004_exposures_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hedge_exposures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("hedge_id", sa.Integer(), sa.ForeignKey("hedges.id"), nullable=False),
        sa.Column("exposure_id", sa.Integer(), sa.ForeignKey("exposures.id"), nullable=False),
        sa.Column("quantity_mt", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("hedges", sa.Column("instrument", sa.String(length=128), nullable=True))
    op.add_column("hedges", sa.Column("maturity_date", sa.Date(), nullable=True))
    op.add_column("hedges", sa.Column("reference_code", sa.String(length=128), nullable=True))
    with op.batch_alter_table("hedges") as batch_op:
        batch_op.alter_column("so_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("hedges") as batch_op:
        batch_op.alter_column("so_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("hedges", "reference_code")
    op.drop_column("hedges", "maturity_date")
    op.drop_column("hedges", "instrument")
    op.drop_table("hedge_exposures")
