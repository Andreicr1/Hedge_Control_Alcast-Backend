"""add idempotency and retry markers to rfq send attempts

Revision ID: 20231221_0010
Revises: 20231221_0009_add_fx_flag_market_prices
Create Date: 2024-01-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20231221_0010_rfq_idempotency_retry"
down_revision = "20231221_0009_fx_flag_market_prices"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rfq_send_attempts", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("rfq_send_attempts", sa.Column("retry_of_attempt_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_rfq_send_attempt_idempotency",
        "rfq_send_attempts",
        ["rfq_id", "idempotency_key"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_rfq_send_attempt_idempotency", table_name="rfq_send_attempts")
    op.drop_column("rfq_send_attempts", "retry_of_attempt_id")
    op.drop_column("rfq_send_attempts", "idempotency_key")
