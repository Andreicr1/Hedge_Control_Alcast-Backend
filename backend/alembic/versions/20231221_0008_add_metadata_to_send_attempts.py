"""add metadata to send attempts

Revision ID: 20231221_0008
Revises: 20231221_0007
Create Date: 2023-12-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20231221_0008_rfq_send_metadata"
down_revision = "20231221_0007_add_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfq_send_attempts", sa.Column("metadata_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rfq_send_attempts", "metadata_json")
