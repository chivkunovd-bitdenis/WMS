"""FBS warehouse binding, stock sync items, and FbsOrder warehouse fields.

Revision ID: 20260802_0068
Revises: 20260731_0067
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0068"
down_revision: str | Sequence[str] | None = "20260731_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fbs_warehouse_bindings",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("wb_warehouse_id", sa.BigInteger(), nullable=False),
        sa.Column("wms_warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("stock_sync_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(length=32), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wms_warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "seller_id",
            "wb_warehouse_id",
            name="uq_fbs_warehouse_bindings_seller_wb_warehouse",
        ),
        sa.UniqueConstraint(
            "seller_id",
            "wms_warehouse_id",
            name="uq_fbs_warehouse_bindings_seller_wms_warehouse",
        ),
    )
    op.create_index(
        "ix_fbs_warehouse_bindings_tenant_id",
        "fbs_warehouse_bindings",
        ["tenant_id"],
    )
    op.create_index(
        "ix_fbs_warehouse_bindings_seller_id",
        "fbs_warehouse_bindings",
        ["seller_id"],
    )
    op.create_index(
        "ix_fbs_warehouse_bindings_wb_warehouse_id",
        "fbs_warehouse_bindings",
        ["wb_warehouse_id"],
    )
    op.create_index(
        "ix_fbs_warehouse_bindings_wms_warehouse_id",
        "fbs_warehouse_bindings",
        ["wms_warehouse_id"],
    )

    op.create_table(
        "fbs_stock_sync_items",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("binding_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("chrt_id", sa.BigInteger(), nullable=False),
        sa.Column("last_target_amount", sa.Integer(), nullable=True),
        sa.Column("last_confirmed_amount", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["fbs_warehouse_bindings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "binding_id",
            "chrt_id",
            name="uq_fbs_stock_sync_items_binding_chrt",
        ),
    )
    op.create_index(
        "ix_fbs_stock_sync_items_binding_id",
        "fbs_stock_sync_items",
        ["binding_id"],
    )
    op.create_index(
        "ix_fbs_stock_sync_items_product_id",
        "fbs_stock_sync_items",
        ["product_id"],
    )
    op.create_index(
        "ix_fbs_stock_sync_items_chrt_id",
        "fbs_stock_sync_items",
        ["chrt_id"],
    )

    op.add_column(
        "fbs_orders",
        sa.Column("wb_warehouse_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_fbs_orders_wb_warehouse_id",
        "fbs_orders",
        ["wb_warehouse_id"],
    )
    op.alter_column(
        "fbs_orders",
        "warehouse_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "fbs_orders",
        "warehouse_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
    op.drop_index("ix_fbs_orders_wb_warehouse_id", table_name="fbs_orders")
    op.drop_column("fbs_orders", "wb_warehouse_id")

    op.drop_index("ix_fbs_stock_sync_items_chrt_id", table_name="fbs_stock_sync_items")
    op.drop_index("ix_fbs_stock_sync_items_product_id", table_name="fbs_stock_sync_items")
    op.drop_index("ix_fbs_stock_sync_items_binding_id", table_name="fbs_stock_sync_items")
    op.drop_table("fbs_stock_sync_items")

    op.drop_index(
        "ix_fbs_warehouse_bindings_wms_warehouse_id",
        table_name="fbs_warehouse_bindings",
    )
    op.drop_index(
        "ix_fbs_warehouse_bindings_wb_warehouse_id",
        table_name="fbs_warehouse_bindings",
    )
    op.drop_index(
        "ix_fbs_warehouse_bindings_seller_id",
        table_name="fbs_warehouse_bindings",
    )
    op.drop_index(
        "ix_fbs_warehouse_bindings_tenant_id",
        table_name="fbs_warehouse_bindings",
    )
    op.drop_table("fbs_warehouse_bindings")
