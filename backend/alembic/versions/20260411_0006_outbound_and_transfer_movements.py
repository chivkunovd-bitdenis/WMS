"""outbound shipment, stock transfer, nullable movement refs

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outbound_shipment_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_outbound_shipment_requests_tenant_id"),
        "outbound_shipment_requests",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_outbound_shipment_requests_warehouse_id"),
        "outbound_shipment_requests",
        ["warehouse_id"],
    )

    op.create_table(
        "outbound_shipment_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["outbound_shipment_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["storage_location_id"], ["storage_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "product_id",
            name="uq_outbound_shipment_line_req_product",
        ),
    )
    op.create_index(
        op.f("ix_outbound_shipment_lines_request_id"),
        "outbound_shipment_lines",
        ["request_id"],
    )
    op.create_index(
        op.f("ix_outbound_shipment_lines_product_id"),
        "outbound_shipment_lines",
        ["product_id"],
    )
    op.create_index(
        op.f("ix_outbound_shipment_lines_storage_location_id"),
        "outbound_shipment_lines",
        ["storage_location_id"],
    )

    op.add_column(
        "inventory_movements",
        sa.Column("outbound_shipment_line_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "inventory_movements",
        sa.Column("transfer_group_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.alter_column(
        "inventory_movements",
        "inbound_intake_line_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
    )
    op.create_index(
        op.f("ix_inventory_movements_outbound_shipment_line_id"),
        "inventory_movements",
        ["outbound_shipment_line_id"],
    )
    op.create_index(
        op.f("ix_inventory_movements_transfer_group_id"),
        "inventory_movements",
        ["transfer_group_id"],
    )
    op.create_foreign_key(
        "fk_inventory_movements_outbound_shipment_line_id",
        "inventory_movements",
        "outbound_shipment_lines",
        ["outbound_shipment_line_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inventory_movements_outbound_shipment_line_id",
        "inventory_movements",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_inventory_movements_transfer_group_id"),
        table_name="inventory_movements",
    )
    op.drop_index(
        op.f("ix_inventory_movements_outbound_shipment_line_id"),
        table_name="inventory_movements",
    )
    op.alter_column(
        "inventory_movements",
        "inbound_intake_line_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
    op.drop_column("inventory_movements", "transfer_group_id")
    op.drop_column("inventory_movements", "outbound_shipment_line_id")
    op.drop_index(
        op.f("ix_outbound_shipment_lines_storage_location_id"),
        table_name="outbound_shipment_lines",
    )
    op.drop_index(
        op.f("ix_outbound_shipment_lines_product_id"),
        table_name="outbound_shipment_lines",
    )
    op.drop_index(
        op.f("ix_outbound_shipment_lines_request_id"),
        table_name="outbound_shipment_lines",
    )
    op.drop_table("outbound_shipment_lines")
    op.drop_index(
        op.f("ix_outbound_shipment_requests_warehouse_id"),
        table_name="outbound_shipment_requests",
    )
    op.drop_index(
        op.f("ix_outbound_shipment_requests_tenant_id"),
        table_name="outbound_shipment_requests",
    )
    op.drop_table("outbound_shipment_requests")
