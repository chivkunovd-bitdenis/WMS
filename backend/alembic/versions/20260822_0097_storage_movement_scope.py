"""Add immutable warehouse scope required by storage measurements."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260822_0097"
down_revision = "20260822_0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "warehouses",
        sa.Column("is_operational", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("inventory_movements", sa.Column("warehouse_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_inventory_movements_warehouse_id",
        "inventory_movements",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_inventory_movements_warehouse_id", "inventory_movements", ["warehouse_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_movements_warehouse_id", table_name="inventory_movements")
    op.drop_constraint(
        "fk_inventory_movements_warehouse_id", "inventory_movements", type_="foreignkey"
    )
    op.drop_column("inventory_movements", "warehouse_id")
    op.drop_column("warehouses", "is_operational")
