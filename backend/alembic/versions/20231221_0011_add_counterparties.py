"""add counterparties table

Revision ID: 20231221_0011
Revises: 20231221_0010
Create Date: 2024-01-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20231221_0011_add_counterparties"
down_revision = "20231221_0010_rfq_idempotency_retry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "counterparties",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("preferred_channel", sa.String(length=32), nullable=False, server_default="api"),
        sa.Column("api_endpoint", sa.String(length=512), nullable=True),
        sa.Column("api_headers_json", sa.Text(), nullable=True),
        sa.Column("credit_limit", sa.Float(), nullable=True),
        sa.Column("credit_limit_currency", sa.String(length=8), nullable=True),
        sa.Column("credit_expiry", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("counterparties")
