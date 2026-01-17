"""Add rfq_channel_type and invitation message"""

from alembic import op
import sqlalchemy as sa


revision = "20250111_0009_rfq_channel_message"
down_revision = "20250111_0008_rfq_award"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("counterparties", sa.Column("rfq_channel_type", sa.String(length=32), server_default="BROKER_LME"))
    op.add_column("rfq_invitations", sa.Column("message_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rfq_invitations", "message_text")
    op.drop_column("counterparties", "rfq_channel_type")
