"""add treasury decisions and kyc overrides

Revision ID: 20260119_0001_add_treasury_decisions
Revises: 20260118_0004_expand_lme_price_type_close
Create Date: 2026-01-19
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260119_0001_add_treasury_decisions"
down_revision = "20260118_0004_expand_lme_price_type_close"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "treasury_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exposure_id", sa.Integer(), sa.ForeignKey("exposures.id"), nullable=False),
        sa.Column("decision_kind", sa.String(length=32), nullable=False, index=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("kyc_gate_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "treasury_kyc_overrides",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "decision_id",
            sa.Integer(),
            sa.ForeignKey("treasury_decisions.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.create_check_constraint(
            "ck_treasury_decisions_kind",
            "treasury_decisions",
            "decision_kind in ('hedge','do_not_hedge','roll','close')",
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE treasury_decisions DROP CONSTRAINT IF EXISTS ck_treasury_decisions_kind"
        )

    op.drop_table("treasury_kyc_overrides")
    op.drop_table("treasury_decisions")
