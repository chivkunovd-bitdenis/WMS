"""Freeze seller and warehouse dimensions on inventory movements."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0094"
down_revision: str | Sequence[str] | None = "20260821_0094"
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

    # Resolve historical dimensions once. Storage calculations must never
    # derive their warehouse later through a mutable location relationship.
    op.execute(
        sa.text(
            """
            UPDATE inventory_movements AS movement
            SET seller_id = (
                    SELECT product.seller_id
                    FROM products AS product
                    WHERE product.id = movement.product_id
                ),
                warehouse_id = (
                    SELECT location.warehouse_id
                    FROM storage_locations AS location
                    WHERE location.id = movement.storage_location_id
                ),
                reporting_dimensions_legacy = (
                    NOT EXISTS (
                        SELECT 1
                        FROM products AS product
                        WHERE product.id = movement.product_id
                          AND product.seller_id IS NOT NULL
                    )
                    OR NOT EXISTS (
                        SELECT 1
                        FROM storage_locations AS location
                        WHERE location.id = movement.storage_location_id
                          AND location.warehouse_id IS NOT NULL
                    )
                )
            """
        )
    )
    # A missing warehouse makes a movement unusable for physical storage and
    # must stop deployment instead of being guessed from unrelated data.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM inventory_movements
                    WHERE warehouse_id IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Unresolved historical warehouse for inventory movement';
                END IF;
            END $$;
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
    op.drop_index(
        "ix_inventory_movements_tenant_warehouse_created_at",
        table_name="inventory_movements",
    )
    op.drop_index(
        "ix_inventory_movements_tenant_seller_created_at",
        table_name="inventory_movements",
    )
    op.drop_index(
        "ix_inventory_movements_tenant_created_at",
        table_name="inventory_movements",
    )
    op.drop_constraint(
        "fk_inventory_movements_warehouse_id",
        "inventory_movements",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_inventory_movements_seller_id",
        "inventory_movements",
        type_="foreignkey",
    )
    op.drop_column("inventory_movements", "reporting_dimensions_legacy")
    op.drop_column("inventory_movements", "warehouse_id")
    op.drop_column("inventory_movements", "seller_id")
