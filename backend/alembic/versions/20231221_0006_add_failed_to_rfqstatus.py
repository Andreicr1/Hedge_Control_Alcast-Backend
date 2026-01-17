"""add failed to rfqstatus

Revision ID: 20231221_0006
Revises: 20231221_0005
Create Date: 2023-12-21
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20231221_0006_rfq_failed_status"
down_revision = "20231221_0005_rfq_send_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE rfqstatus ADD VALUE IF NOT EXISTS 'failed'")


def downgrade() -> None:
    # removing enum values is not trivial; left as-is
    pass
