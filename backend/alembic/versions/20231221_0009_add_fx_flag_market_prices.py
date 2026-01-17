"""add fx flag to market_prices

Revision ID: 20231221_0009
Revises: 20231221_0008
Create Date: 2023-12-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20231221_0009_fx_flag_market_prices"
down_revision = "20231221_0008_rfq_send_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_prices", sa.Column("fx", sa.Boolean(), server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("market_prices", "fx")
