"""FBS supply assembly: fbs_supplies, order supply FK, stickers.

Revision ID: 20260730_0064
Revises: 20260730_0063
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_0064"
down_revision = "20260730_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fbs_supplies",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("wb_supply_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("delivery_type", sa.String(length=32), nullable=False),
        sa.Column("cargo_type", sa.String(length=16), nullable=True),
        sa.Column("wb_office_id", sa.Integer(), nullable=True),
        sa.Column("barcode_file", sa.String(length=512), nullable=True),
        sa.Column("document_number", sa.String(length=64), nullable=True),
        sa.Column("display_number", sa.String(length=64), nullable=True),
        sa.Column("created_at_wb", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fbs_supplies_tenant_id", "fbs_supplies", ["tenant_id"])
    op.create_index("ix_fbs_supplies_seller_id", "fbs_supplies", ["seller_id"])
    op.create_index("ix_fbs_supplies_warehouse_id", "fbs_supplies", ["warehouse_id"])
    op.create_index("ix_fbs_supplies_wb_supply_id", "fbs_supplies", ["wb_supply_id"])

    op.create_foreign_key(
        "fk_fbs_orders_supply_id",
        "fbs_orders",
        "fbs_supplies",
        ["supply_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_fbs_orders_supply_id", "fbs_orders", ["supply_id"])
    op.add_column("fbs_orders", sa.Column("sticker_code", sa.String(length=128), nullable=True))
    op.add_column("fbs_orders", sa.Column("sticker_file", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("fbs_orders", "sticker_file")
    op.drop_column("fbs_orders", "sticker_code")
    op.drop_index("ix_fbs_orders_supply_id", table_name="fbs_orders")
    op.drop_constraint("fk_fbs_orders_supply_id", "fbs_orders", type_="foreignkey")
    op.drop_index("ix_fbs_supplies_wb_supply_id", table_name="fbs_supplies")
    op.drop_index("ix_fbs_supplies_warehouse_id", table_name="fbs_supplies")
    op.drop_index("ix_fbs_supplies_seller_id", table_name="fbs_supplies")
    op.drop_index("ix_fbs_supplies_tenant_id", table_name="fbs_supplies")
    op.drop_table("fbs_supplies")
