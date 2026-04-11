"""inbound line storage, posted_qty, inventory movements

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_lines",
        sa.Column("posted_qty", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inbound_intake_lines",
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_inbound_intake_lines_storage_location_id"),
        "inbound_intake_lines",
        ["storage_location_id"],
    )
    op.create_foreign_key(
        "fk_inbound_intake_lines_storage_location_id",
        "inbound_intake_lines",
        "storage_locations",
        ["storage_location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("movement_type", sa.String(length=64), nullable=False),
        sa.Column("inbound_intake_line_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["storage_location_id"], ["storage_locations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["inbound_intake_line_id"],
            ["inbound_intake_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inventory_movements_tenant_id"),
        "inventory_movements",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_inventory_movements_product_id"),
        "inventory_movements",
        ["product_id"],
    )
    op.create_index(
        op.f("ix_inventory_movements_storage_location_id"),
        "inventory_movements",
        ["storage_location_id"],
    )
    op.create_index(
        op.f("ix_inventory_movements_inbound_intake_line_id"),
        "inventory_movements",
        ["inbound_intake_line_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_inventory_movements_inbound_intake_line_id"),
        table_name="inventory_movements",
    )
    op.drop_index(
        op.f("ix_inventory_movements_storage_location_id"),
        table_name="inventory_movements",
    )
    op.drop_index(
        op.f("ix_inventory_movements_product_id"),
        table_name="inventory_movements",
    )
    op.drop_index(
        op.f("ix_inventory_movements_tenant_id"),
        table_name="inventory_movements",
    )
    op.drop_table("inventory_movements")
    op.drop_constraint(
        "fk_inbound_intake_lines_storage_location_id",
        "inbound_intake_lines",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_inbound_intake_lines_storage_location_id"),
        table_name="inbound_intake_lines",
    )
    op.drop_column("inbound_intake_lines", "storage_location_id")
    op.drop_column("inbound_intake_lines", "posted_qty")
