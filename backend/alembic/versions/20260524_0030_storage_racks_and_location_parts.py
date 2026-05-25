"""warehouse storage racks and rack-side-position on locations

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-24

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, Sequence[str], None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouse_storage_racks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "warehouse_id", "name", name="uq_warehouse_storage_racks_wh_name"
        ),
    )
    op.create_index(
        op.f("ix_warehouse_storage_racks_tenant_id"),
        "warehouse_storage_racks",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_warehouse_storage_racks_warehouse_id"),
        "warehouse_storage_racks",
        ["warehouse_id"],
        unique=False,
    )

    op.add_column(
        "storage_locations",
        sa.Column("rack_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column("storage_locations", sa.Column("side", sa.Integer(), nullable=True))
    op.add_column(
        "storage_locations", sa.Column("position", sa.Integer(), nullable=True)
    )
    op.create_index(
        op.f("ix_storage_locations_rack_id"),
        "storage_locations",
        ["rack_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_storage_locations_rack_id",
        "storage_locations",
        "warehouse_storage_racks",
        ["rack_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_storage_locations_rack_id", "storage_locations", type_="foreignkey"
    )
    op.drop_index(op.f("ix_storage_locations_rack_id"), table_name="storage_locations")
    op.drop_column("storage_locations", "position")
    op.drop_column("storage_locations", "side")
    op.drop_column("storage_locations", "rack_id")

    op.drop_index(
        op.f("ix_warehouse_storage_racks_warehouse_id"),
        table_name="warehouse_storage_racks",
    )
    op.drop_index(
        op.f("ix_warehouse_storage_racks_tenant_id"),
        table_name="warehouse_storage_racks",
    )
    op.drop_table("warehouse_storage_racks")

