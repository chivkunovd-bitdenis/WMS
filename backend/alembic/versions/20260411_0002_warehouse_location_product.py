"""warehouse location product

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
    )
    op.create_index(op.f("ix_warehouses_tenant_id"), "warehouses", ["tenant_id"])

    op.create_table(
        "storage_locations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "warehouse_id", "code", name="uq_storage_locations_wh_code"
        ),
    )
    op.create_index(
        op.f("ix_storage_locations_tenant_id"), "storage_locations", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_storage_locations_warehouse_id"),
        "storage_locations",
        ["warehouse_id"],
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sku_code", sa.String(length=128), nullable=False),
        sa.Column("length_mm", sa.Integer(), nullable=False),
        sa.Column("width_mm", sa.Integer(), nullable=False),
        sa.Column("height_mm", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sku_code", name="uq_products_tenant_sku"),
    )
    op.create_index(op.f("ix_products_tenant_id"), "products", ["tenant_id"])
    op.create_index(op.f("ix_products_seller_id"), "products", ["seller_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_products_seller_id"), table_name="products")
    op.drop_index(op.f("ix_products_tenant_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_storage_locations_warehouse_id"), table_name="storage_locations")
    op.drop_index(op.f("ix_storage_locations_tenant_id"), table_name="storage_locations")
    op.drop_table("storage_locations")
    op.drop_index(op.f("ix_warehouses_tenant_id"), table_name="warehouses")
    op.drop_table("warehouses")
