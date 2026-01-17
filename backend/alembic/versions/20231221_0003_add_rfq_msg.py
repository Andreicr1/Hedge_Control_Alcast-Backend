"""add rfq message_text

Revision ID: 20231221_0003
Revises: 20231221_0002
Create Date: 2023-12-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20231221_0003_add_rfq_msg"
down_revision = "20231221_0002_seed_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rfqs", sa.Column("message_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rfqs", "message_text")
