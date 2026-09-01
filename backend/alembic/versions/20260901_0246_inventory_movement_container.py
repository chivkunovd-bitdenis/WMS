"""Record the physical container on every inventory movement.

Revision ID: 20260901_0246
Revises: 20260901_0245
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0246"
down_revision: str | Sequence[str] | None = "20260901_0245"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_movements",
        sa.Column("container_kind", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "inventory_movements",
        sa.Column("container_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_inventory_movements_container_kind",
        "inventory_movements",
        ["container_kind"],
    )
    op.create_index(
        "ix_inventory_movements_container_id",
        "inventory_movements",
        ["container_id"],
    )
    op.create_check_constraint(
        "ck_inventory_movements_container_pair",
        "inventory_movements",
        "(container_kind IS NULL AND container_id IS NULL) OR "
        "(container_kind IS NOT NULL AND container_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_inventory_movements_container_kind",
        "inventory_movements",
        "container_kind IS NULL OR container_kind IN ('pallet', 'box', 'cargo_place')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_inventory_movements_container_kind",
        "inventory_movements",
        type_="check",
    )
    op.drop_constraint(
        "ck_inventory_movements_container_pair",
        "inventory_movements",
        type_="check",
    )
    op.drop_index(
        "ix_inventory_movements_container_id",
        table_name="inventory_movements",
    )
    op.drop_index(
        "ix_inventory_movements_container_kind",
        table_name="inventory_movements",
    )
    op.drop_column("inventory_movements", "container_id")
    op.drop_column("inventory_movements", "container_kind")
