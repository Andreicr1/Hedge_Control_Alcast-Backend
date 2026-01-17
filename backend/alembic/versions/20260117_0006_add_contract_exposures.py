"""add contract_exposures link table

Revision ID: 20260117_0006_add_contract_exposures
Revises: 20260117_0005_enforce_deal_linkage_not_null
Create Date: 2026-01-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260117_0006_add_contract_exposures"
down_revision = "20260117_0005_enforce_deal_linkage_not_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_exposures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("exposure_id", sa.Integer(), nullable=False),
        sa.Column("quantity_mt", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"]),
        sa.ForeignKeyConstraint(["exposure_id"], ["exposures.id"]),
        sa.UniqueConstraint("contract_id", "exposure_id", name="uq_contract_exposures"),
    )
    op.create_index(
        "ix_contract_exposures_contract_id",
        "contract_exposures",
        ["contract_id"],
    )
    op.create_index(
        "ix_contract_exposures_exposure_id",
        "contract_exposures",
        ["exposure_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contract_exposures_exposure_id", table_name="contract_exposures")
    op.drop_index("ix_contract_exposures_contract_id", table_name="contract_exposures")
    op.drop_table("contract_exposures")
