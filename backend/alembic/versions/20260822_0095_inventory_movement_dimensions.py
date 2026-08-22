"""Persist seller and warehouse dimensions on inventory movements."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260822_0095"
down_revision: str | Sequence[str] | None = "20260822_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_movements", sa.Column("seller_id", sa.Uuid(), nullable=True))
    op.add_column("inventory_movements", sa.Column("warehouse_id", sa.Uuid(), nullable=True))
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE inventory_movements "
            "SET seller_id = (SELECT seller_id FROM products WHERE products.id = inventory_movements.product_id), "
            "warehouse_id = (SELECT warehouse_id FROM storage_locations "
            "WHERE storage_locations.id = inventory_movements.storage_location_id)"
        )
    )
    # Products may legitimately have no seller (ordinary FF stock).  Keep those
    # historical and new movements writable; FBS movements still carry seller_id.
    op.alter_column("inventory_movements", "seller_id", nullable=True)
    op.alter_column("inventory_movements", "warehouse_id", nullable=False)
    op.create_index("ix_inventory_movements_seller_id", "inventory_movements", ["seller_id"])
    op.create_index("ix_inventory_movements_warehouse_id", "inventory_movements", ["warehouse_id"])


def downgrade() -> None:
    op.drop_index("ix_inventory_movements_warehouse_id", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_seller_id", table_name="inventory_movements")
    op.drop_column("inventory_movements", "warehouse_id")
    op.drop_column("inventory_movements", "seller_id")
