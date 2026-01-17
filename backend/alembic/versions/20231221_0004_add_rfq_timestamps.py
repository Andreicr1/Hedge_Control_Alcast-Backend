"""add rfq timestamps

Revision ID: 20231221_0004
Revises: 20231221_0003
Create Date: 2023-12-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20231221_0004_add_rfq_timestamps"
down_revision = "20231221_0003_add_rfq_msg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfqs", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rfqs", sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("rfqs", "awarded_at")
    op.drop_column("rfqs", "sent_at")
