"""warehouse-level outbound inventory reservations

Revision ID: 0032
Revises: 0031
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, Sequence[str], None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_reservations",
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_reservations_warehouse_id",
        "inventory_reservations",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_inventory_reservations_tenant_wh_product",
        "inventory_reservations",
        ["tenant_id", "warehouse_id", "product_id"],
        unique=False,
    )
    with op.batch_alter_table("inventory_reservations") as batch_op:
        batch_op.alter_column("storage_location_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_reservations_tenant_wh_product",
        table_name="inventory_reservations",
    )
    op.drop_constraint(
        "fk_inventory_reservations_warehouse_id",
        "inventory_reservations",
        type_="foreignkey",
    )
    op.drop_column("inventory_reservations", "warehouse_id")
    with op.batch_alter_table("inventory_reservations") as batch_op:
        batch_op.alter_column("storage_location_id", existing_type=sa.Uuid(), nullable=False)
