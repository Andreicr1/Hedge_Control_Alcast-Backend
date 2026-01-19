"""expand lme_prices price_type to include close

Revision ID: 20260118_0004_expand_lme_price_type_close
Revises: 20260118_0003_add_lme_prices
Create Date: 2026-01-18
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260118_0004_expand_lme_price_type_close"
down_revision = "20260118_0003_add_lme_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # SQLite doesn't support dropping constraints easily; dev/tests mainly rely on
    # Pydantic validation for price_type. Postgres is the production target.
    if dialect != "postgresql":
        return

    # Drop the old constraint (if it exists) and recreate with the expanded enum.
    op.execute("ALTER TABLE lme_prices DROP CONSTRAINT IF EXISTS ck_lme_prices_price_type")
    op.create_check_constraint(
        "ck_lme_prices_price_type",
        "lme_prices",
        "price_type in ('live','close','official')",
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect != "postgresql":
        return

    op.execute("ALTER TABLE lme_prices DROP CONSTRAINT IF EXISTS ck_lme_prices_price_type")
    op.create_check_constraint(
        "ck_lme_prices_price_type",
        "lme_prices",
        "price_type in ('live','official')",
    )
