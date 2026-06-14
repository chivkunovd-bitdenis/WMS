"""products: wb size variant fields (barcode, chrt_id, size)

Revision ID: 20260614_0039
Revises: 20260611_0038
Create Date: 2026-06-14

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260614_0039"
down_revision = "20260611_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("wb_chrt_id", sa.BigInteger(), nullable=True))
    op.add_column("products", sa.Column("wb_barcode", sa.String(length=64), nullable=True))
    op.add_column("products", sa.Column("wb_size", sa.String(length=64), nullable=True))
    op.drop_constraint("uq_products_tenant_wb_nm_id", "products", type_="unique")
    op.create_index(op.f("ix_products_wb_barcode"), "products", ["wb_barcode"], unique=False)
    op.create_unique_constraint(
        "uq_products_tenant_wb_barcode",
        "products",
        ["tenant_id", "wb_barcode"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_products_tenant_wb_barcode", "products", type_="unique")
    op.drop_index(op.f("ix_products_wb_barcode"), table_name="products")
    op.create_unique_constraint(
        "uq_products_tenant_wb_nm_id",
        "products",
        ["tenant_id", "wb_nm_id"],
    )
    op.drop_column("products", "wb_size")
    op.drop_column("products", "wb_barcode")
    op.drop_column("products", "wb_chrt_id")
