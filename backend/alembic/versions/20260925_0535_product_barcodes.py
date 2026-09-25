"""Store every WB barcode for a product size.

Revision ID: 20260925_0535
Revises: 20260924_0526
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260925_0535"
down_revision: str | Sequence[str] | None = "20260924_0526"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_products_tenant_seller_wb_chrt_id",
        "products",
        ["tenant_id", "seller_id", "wb_chrt_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_products_tenant_seller_id",
        "products",
        ["tenant_id", "seller_id", "id"],
    )
    op.create_table(
        "product_barcodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="wb", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "seller_id", "product_id"],
            ["products.tenant_id", "products.seller_id", "products.id"],
            name="fk_product_barcodes_product_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "barcode",
            name="uq_product_barcodes_tenant_seller_barcode",
        ),
    )
    op.create_index(
        "ix_product_barcodes_product_id",
        "product_barcodes",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_product_barcodes_tenant_barcode",
        "product_barcodes",
        ["tenant_id", "barcode"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO product_barcodes (
                id, tenant_id, seller_id, product_id, barcode, source
            )
            SELECT
                gen_random_uuid(),
                products.tenant_id,
                products.seller_id,
                products.id,
                btrim(products.wb_barcode),
                'wb'
            FROM products
            WHERE products.seller_id IS NOT NULL
              AND NULLIF(btrim(products.wb_barcode), '') IS NOT NULL
            ON CONFLICT (tenant_id, seller_id, barcode) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_product_barcodes_tenant_barcode", table_name="product_barcodes")
    op.drop_index("ix_product_barcodes_product_id", table_name="product_barcodes")
    op.drop_table("product_barcodes")
    op.drop_constraint("uq_products_tenant_seller_id", "products", type_="unique")
    op.drop_index("ix_products_tenant_seller_wb_chrt_id", table_name="products")
