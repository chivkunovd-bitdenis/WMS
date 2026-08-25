"""store Ozon return giveouts and their imported items for inbound intake

Revision ID: 20260825_0106
Revises: 20260825_0105
"""

import sqlalchemy as sa

from alembic import op

revision = "20260825_0106"
down_revision = "20260825_0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_requests",
        sa.Column("marketplace", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "inbound_intake_lines",
        sa.Column("defective_qty", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "inbound_ozon_return_giveouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("giveout_id", sa.BigInteger(), nullable=False),
        sa.Column("giveout_status", sa.String(length=64), nullable=False),
        sa.Column("warehouse_external_id", sa.BigInteger(), nullable=True),
        sa.Column("warehouse_name", sa.String(length=255), nullable=False),
        sa.Column("warehouse_address", sa.String(length=512), nullable=False),
        sa.Column("approved_articles_count", sa.Integer(), nullable=False),
        sa.Column("total_articles_count", sa.Integer(), nullable=False),
        sa.Column("storage_days", sa.Integer(), nullable=True),
        sa.Column("utilization_forecast_date", sa.Date(), nullable=True),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["inbound_intake_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "giveout_id",
            name="uq_inbound_ozon_return_giveout_request",
        ),
    )
    op.create_index(
        "ix_inbound_ozon_return_giveouts_tenant_id",
        "inbound_ozon_return_giveouts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inbound_ozon_return_giveouts_request_id",
        "inbound_ozon_return_giveouts",
        ["request_id"],
    )
    op.create_table(
        "inbound_ozon_return_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("giveout_record_id", sa.Uuid(), nullable=False),
        sa.Column("inbound_line_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("external_return_id", sa.BigInteger(), nullable=True),
        sa.Column("posting_number", sa.String(length=128), nullable=True),
        sa.Column("return_barcode", sa.String(length=255), nullable=True),
        sa.Column("return_reason_name", sa.String(length=255), nullable=True),
        sa.Column("return_type", sa.String(length=64), nullable=True),
        sa.Column("offer_id", sa.String(length=255), nullable=True),
        sa.Column("ozon_sku", sa.BigInteger(), nullable=True),
        sa.Column("product_name", sa.String(length=1024), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("approved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("provider_data_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_inbound_ozon_return_item_quantity_positive",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["request_id"], ["inbound_intake_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["giveout_record_id"],
            ["inbound_ozon_return_giveouts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["inbound_line_id"], ["inbound_intake_lines.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "giveout_record_id",
            "source_key",
            name="uq_inbound_ozon_return_item_source",
        ),
    )
    op.create_index(
        "ix_inbound_ozon_return_items_tenant_id",
        "inbound_ozon_return_items",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inbound_ozon_return_items_request_id",
        "inbound_ozon_return_items",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inbound_ozon_return_items_request_id",
        table_name="inbound_ozon_return_items",
    )
    op.drop_index(
        "ix_inbound_ozon_return_items_tenant_id",
        table_name="inbound_ozon_return_items",
    )
    op.drop_table("inbound_ozon_return_items")
    op.drop_index(
        "ix_inbound_ozon_return_giveouts_request_id",
        table_name="inbound_ozon_return_giveouts",
    )
    op.drop_index(
        "ix_inbound_ozon_return_giveouts_tenant_id",
        table_name="inbound_ozon_return_giveouts",
    )
    op.drop_table("inbound_ozon_return_giveouts")
    op.drop_column("inbound_intake_lines", "defective_qty")
    op.drop_column("inbound_intake_requests", "marketplace")
