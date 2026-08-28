"""add marketplace identity to shared FBS entities

Revision ID: 20260825_0102
Revises: 20260825_0101
"""

import sqlalchemy as sa

from alembic import op

revision = "20260825_0102"
down_revision = "20260825_0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fbs_orders",
        sa.Column("marketplace", sa.String(length=32), nullable=False, server_default="wb"),
    )
    op.add_column(
        "fbs_orders", sa.Column("external_order_id", sa.String(length=255), nullable=True)
    )
    op.create_index("ix_fbs_orders_marketplace", "fbs_orders", ["marketplace"])
    op.create_index("ix_fbs_orders_external_order_id", "fbs_orders", ["external_order_id"])
    op.create_unique_constraint(
        "uq_fbs_orders_seller_marketplace_external_order",
        "fbs_orders",
        ["seller_id", "marketplace", "external_order_id"],
    )

    op.add_column(
        "fbs_supplies",
        sa.Column("marketplace", sa.String(length=32), nullable=False, server_default="wb"),
    )
    op.add_column(
        "fbs_supplies", sa.Column("external_supply_id", sa.String(length=255), nullable=True)
    )
    op.create_index("ix_fbs_supplies_marketplace", "fbs_supplies", ["marketplace"])
    op.create_index("ix_fbs_supplies_external_supply_id", "fbs_supplies", ["external_supply_id"])
    op.create_unique_constraint(
        "uq_fbs_supplies_seller_marketplace_external_supply",
        "fbs_supplies",
        ["seller_id", "marketplace", "external_supply_id"],
    )

    op.add_column(
        "fbs_warehouse_bindings",
        sa.Column("marketplace", sa.String(length=32), nullable=False, server_default="wb"),
    )
    op.add_column(
        "fbs_warehouse_bindings",
        sa.Column("external_warehouse_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_fbs_warehouse_bindings_marketplace", "fbs_warehouse_bindings", ["marketplace"]
    )
    op.create_index(
        "ix_fbs_warehouse_bindings_external_warehouse_id",
        "fbs_warehouse_bindings",
        ["external_warehouse_id"],
    )
    op.create_unique_constraint(
        "uq_fbs_warehouse_bindings_seller_marketplace_external",
        "fbs_warehouse_bindings",
        ["seller_id", "marketplace", "external_warehouse_id"],
    )

    op.add_column(
        "marketplace_unload_requests",
        sa.Column("marketplace", sa.String(length=32), nullable=False, server_default="wb"),
    )
    op.add_column(
        "marketplace_unload_requests",
        sa.Column("external_supply_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_marketplace_unload_requests_marketplace",
        "marketplace_unload_requests",
        ["marketplace"],
    )
    op.create_index(
        "ix_marketplace_unload_requests_external_supply_id",
        "marketplace_unload_requests",
        ["external_supply_id"],
    )

    op.create_table(
        "product_marketplace_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("external_product_id", sa.String(length=255), nullable=True),
        sa.Column("external_offer_id", sa.String(length=255), nullable=True),
        sa.Column("external_sku", sa.String(length=255), nullable=True),
        sa.Column("external_barcodes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("provider_data", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "product_id",
            "marketplace",
            name="uq_product_marketplace_links_product_provider",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "marketplace",
            "external_product_id",
            name="uq_product_marketplace_links_external_product",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "marketplace",
            "external_sku",
            name="uq_product_marketplace_links_external_sku",
        ),
    )
    op.create_index(
        "ix_product_marketplace_links_tenant_id", "product_marketplace_links", ["tenant_id"]
    )
    op.create_index(
        "ix_product_marketplace_links_seller_id", "product_marketplace_links", ["seller_id"]
    )
    op.create_index(
        "ix_product_marketplace_links_product_id", "product_marketplace_links", ["product_id"]
    )
    op.create_index(
        "ix_product_marketplace_links_external_sku", "product_marketplace_links", ["external_sku"]
    )
    op.create_index(
        "ix_product_marketplace_links_lookup",
        "product_marketplace_links",
        ["tenant_id", "seller_id", "marketplace", "external_offer_id"],
    )


def downgrade() -> None:
    op.drop_table("product_marketplace_links")
    op.drop_constraint(
        "uq_fbs_warehouse_bindings_seller_marketplace_external",
        "fbs_warehouse_bindings",
        type_="unique",
    )
    op.drop_constraint(
        "uq_fbs_supplies_seller_marketplace_external_supply",
        "fbs_supplies",
        type_="unique",
    )
    op.drop_constraint(
        "uq_fbs_orders_seller_marketplace_external_order",
        "fbs_orders",
        type_="unique",
    )
    for table, column, index_name in (
        (
            "marketplace_unload_requests",
            "external_supply_id",
            "ix_marketplace_unload_requests_external_supply_id",
        ),
        (
            "marketplace_unload_requests",
            "marketplace",
            "ix_marketplace_unload_requests_marketplace",
        ),
        (
            "fbs_warehouse_bindings",
            "external_warehouse_id",
            "ix_fbs_warehouse_bindings_external_warehouse_id",
        ),
        ("fbs_warehouse_bindings", "marketplace", "ix_fbs_warehouse_bindings_marketplace"),
        ("fbs_supplies", "external_supply_id", "ix_fbs_supplies_external_supply_id"),
        ("fbs_supplies", "marketplace", "ix_fbs_supplies_marketplace"),
        ("fbs_orders", "external_order_id", "ix_fbs_orders_external_order_id"),
        ("fbs_orders", "marketplace", "ix_fbs_orders_marketplace"),
    ):
        op.drop_index(index_name, table_name=table)
        op.drop_column(table, column)
