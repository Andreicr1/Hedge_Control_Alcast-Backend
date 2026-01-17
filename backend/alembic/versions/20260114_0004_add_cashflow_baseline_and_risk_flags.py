"""add cashflow baseline daily + risk flags (phase 6.3.7)

Revision ID: 20260114_0004_add_cashflow_baseline_and_risk_flags
Revises: 20260114_0003_add_mtm_contract_snapshots
Create Date: 2026-01-14
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260114_0004_add_cashflow_baseline_and_risk_flags"
down_revision = "20260114_0003_add_mtm_contract_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cashflow_baseline_runs",
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
        sa.UniqueConstraint("inputs_hash", name="uq_cashflow_baseline_runs_inputs_hash"),
    )
    op.create_index(
        "ix_cashflow_baseline_runs_as_of_date",
        "cashflow_baseline_runs",
        ["as_of_date"],
    )
    op.create_index(
        "ix_cashflow_baseline_runs_inputs_hash",
        "cashflow_baseline_runs",
        ["inputs_hash"],
    )
    op.create_index(
        "ix_cashflow_baseline_runs_requested_by_user_id",
        "cashflow_baseline_runs",
        ["requested_by_user_id"],
    )

    op.create_table(
        "cashflow_baseline_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("rfq_id", sa.Integer(), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("projected_value_usd", sa.Float(), nullable=True),
        sa.Column("projected_methodology", sa.String(length=128), nullable=True),
        sa.Column("projected_as_of", sa.Date(), nullable=True),
        sa.Column("final_value_usd", sa.Float(), nullable=True),
        sa.Column("final_methodology", sa.String(length=128), nullable=True),
        sa.Column("observation_start", sa.Date(), nullable=True),
        sa.Column("observation_end_used", sa.Date(), nullable=True),
        sa.Column("last_published_cash_date", sa.Date(), nullable=True),
        sa.Column("data_quality_flags", sa.JSON(), nullable=True),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["cashflow_baseline_runs.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.contract_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_id",
            "as_of_date",
            "currency",
            name="uq_cashflow_baseline_items_contract_date_currency",
        ),
    )
    op.create_index(
        "ix_cashflow_baseline_items_as_of_date",
        "cashflow_baseline_items",
        ["as_of_date"],
    )
    op.create_index(
        "ix_cashflow_baseline_items_contract_id",
        "cashflow_baseline_items",
        ["contract_id"],
    )
    op.create_index(
        "ix_cashflow_baseline_items_counterparty_id",
        "cashflow_baseline_items",
        ["counterparty_id"],
    )
    op.create_index(
        "ix_cashflow_baseline_items_deal_id",
        "cashflow_baseline_items",
        ["deal_id"],
    )
    op.create_index(
        "ix_cashflow_baseline_items_inputs_hash",
        "cashflow_baseline_items",
        ["inputs_hash"],
    )
    op.create_index(
        "ix_cashflow_baseline_items_rfq_id",
        "cashflow_baseline_items",
        ["rfq_id"],
    )
    op.create_index(
        "ix_cashflow_baseline_items_run_id",
        "cashflow_baseline_items",
        ["run_id"],
    )
    op.create_index(
        "ix_cashflow_baseline_items_settlement_date",
        "cashflow_baseline_items",
        ["settlement_date"],
    )

    op.create_table(
        "finance_risk_flag_runs",
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
        sa.UniqueConstraint("inputs_hash", name="uq_finance_risk_flag_runs_inputs_hash"),
    )
    op.create_index(
        "ix_finance_risk_flag_runs_as_of_date",
        "finance_risk_flag_runs",
        ["as_of_date"],
    )
    op.create_index(
        "ix_finance_risk_flag_runs_inputs_hash",
        "finance_risk_flag_runs",
        ["inputs_hash"],
    )
    op.create_index(
        "ix_finance_risk_flag_runs_requested_by_user_id",
        "finance_risk_flag_runs",
        ["requested_by_user_id"],
    )

    op.create_table(
        "finance_risk_flags",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("flag_code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("message", sa.String(length=256), nullable=True),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["finance_risk_flag_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "subject_type",
            "subject_id",
            "flag_code",
            name="uq_finance_risk_flags_run_subject_flag",
        ),
    )
    op.create_index(
        "ix_finance_risk_flags_as_of_date",
        "finance_risk_flags",
        ["as_of_date"],
    )
    op.create_index(
        "ix_finance_risk_flags_contract_id",
        "finance_risk_flags",
        ["contract_id"],
    )
    op.create_index(
        "ix_finance_risk_flags_deal_id",
        "finance_risk_flags",
        ["deal_id"],
    )
    op.create_index(
        "ix_finance_risk_flags_flag_code",
        "finance_risk_flags",
        ["flag_code"],
    )
    op.create_index(
        "ix_finance_risk_flags_inputs_hash",
        "finance_risk_flags",
        ["inputs_hash"],
    )
    op.create_index(
        "ix_finance_risk_flags_run_id",
        "finance_risk_flags",
        ["run_id"],
    )
    op.create_index(
        "ix_finance_risk_flags_subject_id",
        "finance_risk_flags",
        ["subject_id"],
    )
    op.create_index(
        "ix_finance_risk_flags_subject_type",
        "finance_risk_flags",
        ["subject_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_finance_risk_flags_subject_type", table_name="finance_risk_flags")
    op.drop_index("ix_finance_risk_flags_subject_id", table_name="finance_risk_flags")
    op.drop_index("ix_finance_risk_flags_run_id", table_name="finance_risk_flags")
    op.drop_index("ix_finance_risk_flags_inputs_hash", table_name="finance_risk_flags")
    op.drop_index("ix_finance_risk_flags_flag_code", table_name="finance_risk_flags")
    op.drop_index("ix_finance_risk_flags_deal_id", table_name="finance_risk_flags")
    op.drop_index("ix_finance_risk_flags_contract_id", table_name="finance_risk_flags")
    op.drop_index("ix_finance_risk_flags_as_of_date", table_name="finance_risk_flags")
    op.drop_table("finance_risk_flags")

    op.drop_index(
        "ix_finance_risk_flag_runs_requested_by_user_id",
        table_name="finance_risk_flag_runs",
    )
    op.drop_index(
        "ix_finance_risk_flag_runs_inputs_hash",
        table_name="finance_risk_flag_runs",
    )
    op.drop_index("ix_finance_risk_flag_runs_as_of_date", table_name="finance_risk_flag_runs")
    op.drop_table("finance_risk_flag_runs")

    op.drop_index(
        "ix_cashflow_baseline_items_settlement_date",
        table_name="cashflow_baseline_items",
    )
    op.drop_index("ix_cashflow_baseline_items_run_id", table_name="cashflow_baseline_items")
    op.drop_index("ix_cashflow_baseline_items_rfq_id", table_name="cashflow_baseline_items")
    op.drop_index(
        "ix_cashflow_baseline_items_inputs_hash",
        table_name="cashflow_baseline_items",
    )
    op.drop_index("ix_cashflow_baseline_items_deal_id", table_name="cashflow_baseline_items")
    op.drop_index(
        "ix_cashflow_baseline_items_counterparty_id",
        table_name="cashflow_baseline_items",
    )
    op.drop_index(
        "ix_cashflow_baseline_items_contract_id",
        table_name="cashflow_baseline_items",
    )
    op.drop_index(
        "ix_cashflow_baseline_items_as_of_date",
        table_name="cashflow_baseline_items",
    )
    op.drop_table("cashflow_baseline_items")

    op.drop_index(
        "ix_cashflow_baseline_runs_requested_by_user_id",
        table_name="cashflow_baseline_runs",
    )
    op.drop_index(
        "ix_cashflow_baseline_runs_inputs_hash",
        table_name="cashflow_baseline_runs",
    )
    op.drop_index(
        "ix_cashflow_baseline_runs_as_of_date",
        table_name="cashflow_baseline_runs",
    )
    op.drop_table("cashflow_baseline_runs")
