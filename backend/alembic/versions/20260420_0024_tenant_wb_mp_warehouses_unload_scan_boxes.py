"""Tenant WB MP warehouse cache, unload wb warehouse id, scan boxes/lines."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_wb_mp_warehouses",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("wb_warehouse_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("work_time", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_transit_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "wb_warehouse_id",
            name="uq_tenant_wb_mp_warehouses_tenant_wb",
        ),
    )
    op.create_index(
        op.f("ix_tenant_wb_mp_warehouses_tenant_id"),
        "tenant_wb_mp_warehouses",
        ["tenant_id"],
        unique=False,
    )

    op.add_column(
        "marketplace_unload_requests",
        sa.Column("wb_mp_warehouse_id", sa.Integer(), nullable=True),
    )

    op.create_table(
        "marketplace_unload_boxes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("marketplace_unload_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("box_preset", sa.String(length=32), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_marketplace_unload_boxes_request_id"),
        "marketplace_unload_boxes",
        ["request_id"],
        unique=False,
    )

    op.create_table(
        "marketplace_unload_box_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "box_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("marketplace_unload_boxes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "box_id",
            "product_id",
            name="uq_marketplace_unload_box_line_box_product",
        ),
    )
    op.create_index(
        op.f("ix_marketplace_unload_box_lines_box_id"),
        "marketplace_unload_box_lines",
        ["box_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_marketplace_unload_box_lines_box_id"), table_name="marketplace_unload_box_lines")
    op.drop_table("marketplace_unload_box_lines")
    op.drop_index(op.f("ix_marketplace_unload_boxes_request_id"), table_name="marketplace_unload_boxes")
    op.drop_table("marketplace_unload_boxes")
    op.drop_column("marketplace_unload_requests", "wb_mp_warehouse_id")
    op.drop_index(op.f("ix_tenant_wb_mp_warehouses_tenant_id"), table_name="tenant_wb_mp_warehouses")
    op.drop_table("tenant_wb_mp_warehouses")
