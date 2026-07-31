"""FBS orders intake: fbs_orders, markings, reservations.

Revision ID: 20260730_0062
Revises: 20260710_0061
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_0062"
down_revision = "20260710_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fbs_orders",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("wb_order_id", sa.BigInteger(), nullable=False),
        sa.Column("wb_rid", sa.String(length=128), nullable=True),
        sa.Column("wb_nm_id", sa.BigInteger(), nullable=True),
        sa.Column("wb_chrt_id", sa.BigInteger(), nullable=True),
        sa.Column("wb_article", sa.String(length=255), nullable=True),
        sa.Column("wb_barcode", sa.String(length=64), nullable=True),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("is_legal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("cargo_type", sa.String(length=16), nullable=True),
        sa.Column("wb_office_id", sa.Integer(), nullable=True),
        sa.Column("can_pvz", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supply_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("trbx_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("wb_status", sa.String(length=64), nullable=True),
        sa.Column("created_at_wb", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mapping_status", sa.String(length=32), nullable=False),
        sa.Column("reserve_status", sa.String(length=32), nullable=False),
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
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seller_id", "wb_order_id", name="uq_fbs_orders_seller_wb_order"),
    )
    op.create_index("ix_fbs_orders_tenant_id", "fbs_orders", ["tenant_id"])
    op.create_index("ix_fbs_orders_seller_id", "fbs_orders", ["seller_id"])
    op.create_index("ix_fbs_orders_warehouse_id", "fbs_orders", ["warehouse_id"])
    op.create_index("ix_fbs_orders_product_id", "fbs_orders", ["product_id"])
    op.create_index("ix_fbs_orders_wb_order_id", "fbs_orders", ["wb_order_id"])
    op.create_index("ix_fbs_orders_wb_barcode", "fbs_orders", ["wb_barcode"])

    op.create_table(
        "fbs_order_markings",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("check_status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("marking_code_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["marking_code_id"], ["marking_codes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fbs_order_markings_order_id", "fbs_order_markings", ["order_id"])
    op.create_index(
        "ix_fbs_order_markings_marking_code_id",
        "fbs_order_markings",
        ["marking_code_id"],
    )

    op.create_table(
        "fbs_order_reservations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("fbs_order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["fbs_order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fbs_order_id", name="uq_fbs_order_reservation_order"),
    )
    op.create_index(
        "ix_fbs_order_reservations_tenant_id",
        "fbs_order_reservations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_fbs_order_reservations_product_id",
        "fbs_order_reservations",
        ["product_id"],
    )
    op.create_index(
        "ix_fbs_order_reservations_warehouse_id",
        "fbs_order_reservations",
        ["warehouse_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_fbs_order_reservations_warehouse_id", table_name="fbs_order_reservations")
    op.drop_index("ix_fbs_order_reservations_product_id", table_name="fbs_order_reservations")
    op.drop_index("ix_fbs_order_reservations_tenant_id", table_name="fbs_order_reservations")
    op.drop_table("fbs_order_reservations")
    op.drop_index("ix_fbs_order_markings_marking_code_id", table_name="fbs_order_markings")
    op.drop_index("ix_fbs_order_markings_order_id", table_name="fbs_order_markings")
    op.drop_table("fbs_order_markings")
    op.drop_index("ix_fbs_orders_wb_barcode", table_name="fbs_orders")
    op.drop_index("ix_fbs_orders_wb_order_id", table_name="fbs_orders")
    op.drop_index("ix_fbs_orders_product_id", table_name="fbs_orders")
    op.drop_index("ix_fbs_orders_warehouse_id", table_name="fbs_orders")
    op.drop_index("ix_fbs_orders_seller_id", table_name="fbs_orders")
    op.drop_index("ix_fbs_orders_tenant_id", table_name="fbs_orders")
    op.drop_table("fbs_orders")
