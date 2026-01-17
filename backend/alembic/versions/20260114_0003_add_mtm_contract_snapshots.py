"""add mtm contract snapshots (phase 6.3.6)

Revision ID: 20260114_0003_add_mtm_contract_snapshots
Revises: 20260114_0002_add_finance_pipeline_step_artifacts
Create Date: 2026-01-14
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260114_0003_add_mtm_contract_snapshots"
down_revision = "20260114_0002_add_finance_pipeline_step_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mtm_contract_snapshot_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("scope_filters", sa.JSON(), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inputs_hash", name="uq_mtm_contract_snapshot_runs_inputs_hash"),
    )
    op.create_index(
        "ix_mtm_contract_snapshot_runs_as_of_date",
        "mtm_contract_snapshot_runs",
        ["as_of_date"],
    )
    op.create_index(
        "ix_mtm_contract_snapshot_runs_inputs_hash",
        "mtm_contract_snapshot_runs",
        ["inputs_hash"],
    )
    op.create_index(
        "ix_mtm_contract_snapshot_runs_requested_by_user_id",
        "mtm_contract_snapshot_runs",
        ["requested_by_user_id"],
    )

    op.create_table(
        "mtm_contract_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("mtm_usd", sa.Float(), nullable=False),
        sa.Column("methodology", sa.String(length=128), nullable=True),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["mtm_contract_snapshot_runs.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_id",
            "as_of_date",
            "currency",
            name="uq_mtm_contract_snapshots_contract_date_currency",
        ),
    )
    op.create_index(
        "ix_mtm_contract_snapshots_as_of_date",
        "mtm_contract_snapshots",
        ["as_of_date"],
    )
    op.create_index(
        "ix_mtm_contract_snapshots_contract_id",
        "mtm_contract_snapshots",
        ["contract_id"],
    )
    op.create_index(
        "ix_mtm_contract_snapshots_deal_id",
        "mtm_contract_snapshots",
        ["deal_id"],
    )
    op.create_index(
        "ix_mtm_contract_snapshots_inputs_hash",
        "mtm_contract_snapshots",
        ["inputs_hash"],
    )
    op.create_index(
        "ix_mtm_contract_snapshots_run_id",
        "mtm_contract_snapshots",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mtm_contract_snapshots_run_id", table_name="mtm_contract_snapshots")
    op.drop_index("ix_mtm_contract_snapshots_inputs_hash", table_name="mtm_contract_snapshots")
    op.drop_index("ix_mtm_contract_snapshots_deal_id", table_name="mtm_contract_snapshots")
    op.drop_index(
        "ix_mtm_contract_snapshots_contract_id",
        table_name="mtm_contract_snapshots",
    )
    op.drop_index("ix_mtm_contract_snapshots_as_of_date", table_name="mtm_contract_snapshots")
    op.drop_table("mtm_contract_snapshots")

    op.drop_index(
        "ix_mtm_contract_snapshot_runs_requested_by_user_id",
        table_name="mtm_contract_snapshot_runs",
    )
    op.drop_index(
        "ix_mtm_contract_snapshot_runs_inputs_hash",
        table_name="mtm_contract_snapshot_runs",
    )
    op.drop_index(
        "ix_mtm_contract_snapshot_runs_as_of_date",
        table_name="mtm_contract_snapshot_runs",
    )
    op.drop_table("mtm_contract_snapshot_runs")
