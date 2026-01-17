"""add pnl read models (phase 6.1)

Revision ID: 20260113_0003_add_pnl_read_models
Revises: 20260113_0002_add_export_job_artifacts
Create Date: 2026-01-13
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260113_0003_add_pnl_read_models"
down_revision = "20260113_0002_add_export_job_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    op.create_table(
        "pnl_snapshot_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("scope_filters", sa.JSON(), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pnl_snapshot_runs_as_of_date", "pnl_snapshot_runs", ["as_of_date"])
    op.create_index("ix_pnl_snapshot_runs_inputs_hash", "pnl_snapshot_runs", ["inputs_hash"])
    op.create_index(
        "ix_pnl_snapshot_runs_requested_by_user_id",
        "pnl_snapshot_runs",
        ["requested_by_user_id"],
    )
    if dialect == "sqlite":
        op.create_index(
            "uq_pnl_snapshot_runs_inputs_hash",
            "pnl_snapshot_runs",
            ["inputs_hash"],
            unique=True,
        )
    else:
        op.create_unique_constraint(
            "uq_pnl_snapshot_runs_inputs_hash",
            "pnl_snapshot_runs",
            ["inputs_hash"],
        )

    op.create_table(
        "pnl_contract_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("pnl_snapshot_runs.id"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("contract_id", sa.String(length=36), sa.ForeignKey("contracts.contract_id"), nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="USD", nullable=False),
        sa.Column("unrealized_pnl_usd", sa.Float(), nullable=False),
        sa.Column("methodology", sa.String(length=128), nullable=True),
        sa.Column("data_quality_flags", sa.JSON(), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pnl_contract_snapshots_run_id", "pnl_contract_snapshots", ["run_id"])
    op.create_index("ix_pnl_contract_snapshots_as_of_date", "pnl_contract_snapshots", ["as_of_date"])
    op.create_index("ix_pnl_contract_snapshots_contract_id", "pnl_contract_snapshots", ["contract_id"])
    op.create_index("ix_pnl_contract_snapshots_deal_id", "pnl_contract_snapshots", ["deal_id"])
    op.create_index("ix_pnl_contract_snapshots_inputs_hash", "pnl_contract_snapshots", ["inputs_hash"])
    if dialect == "sqlite":
        op.create_index(
            "uq_pnl_contract_snapshots_contract_date_currency",
            "pnl_contract_snapshots",
            ["contract_id", "as_of_date", "currency"],
            unique=True,
        )
    else:
        op.create_unique_constraint(
            "uq_pnl_contract_snapshots_contract_date_currency",
            "pnl_contract_snapshots",
            ["contract_id", "as_of_date", "currency"],
        )

    op.create_table(
        "pnl_contract_realized",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("contract_id", sa.String(length=36), sa.ForeignKey("contracts.contract_id"), nullable=False),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="USD", nullable=False),
        sa.Column("realized_pnl_usd", sa.Float(), nullable=False),
        sa.Column("methodology", sa.String(length=128), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_hint", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pnl_contract_realized_contract_id", "pnl_contract_realized", ["contract_id"])
    op.create_index("ix_pnl_contract_realized_settlement_date", "pnl_contract_realized", ["settlement_date"])
    op.create_index("ix_pnl_contract_realized_deal_id", "pnl_contract_realized", ["deal_id"])
    op.create_index("ix_pnl_contract_realized_inputs_hash", "pnl_contract_realized", ["inputs_hash"])
    if dialect == "sqlite":
        op.create_index(
            "uq_pnl_contract_realized_contract_settlement_currency",
            "pnl_contract_realized",
            ["contract_id", "settlement_date", "currency"],
            unique=True,
        )
    else:
        op.create_unique_constraint(
            "uq_pnl_contract_realized_contract_settlement_currency",
            "pnl_contract_realized",
            ["contract_id", "settlement_date", "currency"],
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        op.drop_index(
            "uq_pnl_contract_realized_contract_settlement_currency",
            table_name="pnl_contract_realized",
        )
    else:
        op.drop_constraint(
            "uq_pnl_contract_realized_contract_settlement_currency",
            "pnl_contract_realized",
            type_="unique",
        )
    op.drop_index("ix_pnl_contract_realized_inputs_hash", table_name="pnl_contract_realized")
    op.drop_index("ix_pnl_contract_realized_deal_id", table_name="pnl_contract_realized")
    op.drop_index("ix_pnl_contract_realized_settlement_date", table_name="pnl_contract_realized")
    op.drop_index("ix_pnl_contract_realized_contract_id", table_name="pnl_contract_realized")
    op.drop_table("pnl_contract_realized")

    if dialect == "sqlite":
        op.drop_index(
            "uq_pnl_contract_snapshots_contract_date_currency",
            table_name="pnl_contract_snapshots",
        )
    else:
        op.drop_constraint(
            "uq_pnl_contract_snapshots_contract_date_currency",
            "pnl_contract_snapshots",
            type_="unique",
        )
    op.drop_index("ix_pnl_contract_snapshots_inputs_hash", table_name="pnl_contract_snapshots")
    op.drop_index("ix_pnl_contract_snapshots_deal_id", table_name="pnl_contract_snapshots")
    op.drop_index("ix_pnl_contract_snapshots_contract_id", table_name="pnl_contract_snapshots")
    op.drop_index("ix_pnl_contract_snapshots_as_of_date", table_name="pnl_contract_snapshots")
    op.drop_index("ix_pnl_contract_snapshots_run_id", table_name="pnl_contract_snapshots")
    op.drop_table("pnl_contract_snapshots")

    if dialect == "sqlite":
        op.drop_index(
            "uq_pnl_snapshot_runs_inputs_hash",
            table_name="pnl_snapshot_runs",
        )
    else:
        op.drop_constraint(
            "uq_pnl_snapshot_runs_inputs_hash",
            "pnl_snapshot_runs",
            type_="unique",
        )
    op.drop_index("ix_pnl_snapshot_runs_requested_by_user_id", table_name="pnl_snapshot_runs")
    op.drop_index("ix_pnl_snapshot_runs_inputs_hash", table_name="pnl_snapshot_runs")
    op.drop_index("ix_pnl_snapshot_runs_as_of_date", table_name="pnl_snapshot_runs")
    op.drop_table("pnl_snapshot_runs")
