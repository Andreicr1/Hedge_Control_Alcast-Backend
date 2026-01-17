"""enforce deal linkage (deal_id not null for SO/PO/RFQ)

Revision ID: 20260117_0005_enforce_deal_linkage_not_null
Revises: 20260117_0004_add_document_sequences_and_contract_number
Create Date: 2026-01-17
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260117_0005_enforce_deal_linkage_not_null"
down_revision = "20260117_0004_add_document_sequences_and_contract_number"
branch_labels = None
depends_on = None


def _insert_deal(conn: sa.Connection, *, commodity: str | None) -> int:
    deals = sa.table(
        "deals",
        sa.column("id", sa.Integer),
        sa.column("deal_uuid", sa.String),
        sa.column("commodity", sa.String),
        sa.column("currency", sa.String),
        sa.column("status", sa.String),
        sa.column("lifecycle_status", sa.String),
    )

    deal_uuid = str(uuid.uuid4())
    ins = sa.insert(deals).values(
        deal_uuid=deal_uuid,
        commodity=commodity,
        currency="USD",
        status="open",
        lifecycle_status="open",
    )
    result = conn.execute(ins)
    if result.inserted_primary_key:
        return int(result.inserted_primary_key[0])

    # Fallback for dialects that don't populate inserted_primary_key.
    row = conn.execute(
        sa.select(deals.c.id).where(deals.c.deal_uuid == deal_uuid)  # type: ignore[attr-defined]
    ).first()
    if not row:
        raise RuntimeError("Failed to backfill deal")
    return int(row[0])


def upgrade() -> None:
    conn = op.get_bind()

    # Backfill orphan SOs (deal_id is currently nullable in legacy DBs)
    so_rows = conn.execute(
        sa.text(
            "SELECT id, product, total_quantity_mt FROM sales_orders WHERE deal_id IS NULL"
        )
    ).fetchall()
    for so_id, product, qty in so_rows:
        deal_id = _insert_deal(conn, commodity=product)
        conn.execute(
            sa.text("UPDATE sales_orders SET deal_id = :deal_id WHERE id = :id"),
            {"deal_id": deal_id, "id": int(so_id)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO deal_links (deal_id, entity_type, entity_id, direction, quantity_mt, allocation_type) "
                "VALUES (:deal_id, 'so', :entity_id, 'sell', :qty, 'auto')"
            ),
            {"deal_id": deal_id, "entity_id": int(so_id), "qty": float(qty or 0.0)},
        )

    # Backfill orphan POs (should be rare; API already requires deal_id)
    po_rows = conn.execute(
        sa.text(
            "SELECT id, product, total_quantity_mt FROM purchase_orders WHERE deal_id IS NULL"
        )
    ).fetchall()
    for po_id, product, qty in po_rows:
        deal_id = _insert_deal(conn, commodity=product)
        conn.execute(
            sa.text("UPDATE purchase_orders SET deal_id = :deal_id WHERE id = :id"),
            {"deal_id": deal_id, "id": int(po_id)},
        )
        conn.execute(
            sa.text(
                "INSERT INTO deal_links (deal_id, entity_type, entity_id, direction, quantity_mt, allocation_type) "
                "VALUES (:deal_id, 'po', :entity_id, 'buy', :qty, 'auto')"
            ),
            {"deal_id": deal_id, "entity_id": int(po_id), "qty": float(qty or 0.0)},
        )

    # Backfill RFQs by deriving from SO
    conn.execute(
        sa.text(
            "UPDATE rfqs SET deal_id = (SELECT so.deal_id FROM sales_orders so WHERE so.id = rfqs.so_id) "
            "WHERE deal_id IS NULL"
        )
    )

    with op.batch_alter_table("sales_orders") as batch:
        batch.alter_column("deal_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("purchase_orders") as batch:
        batch.alter_column("deal_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("rfqs") as batch:
        batch.alter_column("deal_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("rfqs") as batch:
        batch.alter_column("deal_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("purchase_orders") as batch:
        batch.alter_column("deal_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("sales_orders") as batch:
        batch.alter_column("deal_id", existing_type=sa.Integer(), nullable=True)
