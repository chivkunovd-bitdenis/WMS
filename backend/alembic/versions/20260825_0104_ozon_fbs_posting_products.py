"""store complete Ozon FBS posting composition

Revision ID: 20260825_0104
Revises: 20260825_0103
"""

import sqlalchemy as sa

from alembic import op

revision = "20260825_0104"
down_revision = "20260825_0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fbs_order_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("ozon_sku", sa.BigInteger(), nullable=True),
        sa.Column("offer_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=1024), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("picked_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_data_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "position_index", name="uq_fbs_order_products_position"),
    )
    op.create_index("ix_fbs_order_products_order_id", "fbs_order_products", ["order_id"])
    op.create_index("ix_fbs_order_products_product_id", "fbs_order_products", ["product_id"])
    op.create_table(
        "fbs_order_product_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_product_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_product_id"], ["fbs_order_products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_product_id", name="uq_fbs_order_product_reservation"),
    )
    op.create_index(
        "ix_fbs_order_product_reservations_product",
        "fbs_order_product_reservations",
        ["product_id"],
    )
    op.create_table(
        "fbs_order_product_picks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_product_id", sa.Uuid(), nullable=False),
        sa.Column("fbs_supply_id", sa.Uuid(), nullable=False),
        sa.Column("source_storage_location_id", sa.Uuid(), nullable=False),
        sa.Column("sorting_storage_location_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_movement_id", sa.Uuid(), nullable=True),
        sa.Column("scan_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("undo_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_product_id"], ["fbs_order_products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fbs_supply_id"], ["fbs_supplies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sorting_storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inventory_movement_id"], ["inventory_movements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fbs_supply_id", "scan_idempotency_key", name="uq_fbs_order_product_picks_scan"),
        sa.UniqueConstraint("fbs_supply_id", "undo_idempotency_key", name="uq_fbs_order_product_picks_undo"),
    )
    op.create_index("ix_fbs_order_product_picks_position", "fbs_order_product_picks", ["order_product_id"])


def downgrade() -> None:
    op.drop_index("ix_fbs_order_product_picks_position", table_name="fbs_order_product_picks")
    op.drop_table("fbs_order_product_picks")
    op.drop_index(
        "ix_fbs_order_product_reservations_product",
        table_name="fbs_order_product_reservations",
    )
    op.drop_table("fbs_order_product_reservations")
    op.drop_index("ix_fbs_order_products_product_id", table_name="fbs_order_products")
    op.drop_index("ix_fbs_order_products_order_id", table_name="fbs_order_products")
    op.drop_table("fbs_order_products")
