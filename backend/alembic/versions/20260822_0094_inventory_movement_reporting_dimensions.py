"""Закрепить селлера и склад в факте движения."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260822_0094"
down_revision: str | Sequence[str] | None = "20260821_0093"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_movements",
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "inventory_movements",
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "inventory_movements",
        sa.Column(
            "reporting_dimensions_legacy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_foreign_key(
        "fk_inventory_movements_seller_id",
        "inventory_movements",
        "sellers",
        ["seller_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inventory_movements_warehouse_id",
        "inventory_movements",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # These joins use the immutable links available on the old fact.  A product
    # without a seller remains visible to FF, and is explicitly marked legacy.
    op.execute(
        sa.text(
            """
            UPDATE inventory_movements AS movement
            SET seller_id = product.seller_id,
                warehouse_id = location.warehouse_id,
                reporting_dimensions_legacy = product.seller_id IS NULL
            FROM products AS product
            JOIN storage_locations AS location
              ON location.id = movement.storage_location_id
            WHERE product.id = movement.product_id
            """
        )
    )
    op.alter_column("inventory_movements", "warehouse_id", nullable=False)
    op.alter_column(
        "inventory_movements",
        "reporting_dimensions_legacy",
        server_default=None,
    )
    op.create_index(
        "ix_inventory_movements_tenant_created_at",
        "inventory_movements",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_inventory_movements_tenant_seller_created_at",
        "inventory_movements",
        ["tenant_id", "seller_id", "created_at"],
    )
    op.create_index(
        "ix_inventory_movements_tenant_warehouse_created_at",
        "inventory_movements",
        ["tenant_id", "warehouse_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_movements_tenant_warehouse_created_at", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_tenant_seller_created_at", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_tenant_created_at", table_name="inventory_movements")
    op.drop_constraint("fk_inventory_movements_warehouse_id", "inventory_movements", type_="foreignkey")
    op.drop_constraint("fk_inventory_movements_seller_id", "inventory_movements", type_="foreignkey")
    op.drop_column("inventory_movements", "reporting_dimensions_legacy")
    op.drop_column("inventory_movements", "warehouse_id")
    op.drop_column("inventory_movements", "seller_id")
