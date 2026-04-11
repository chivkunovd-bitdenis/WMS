"""products: wb_nm_id, wb_vendor_code

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("wb_nm_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("wb_vendor_code", sa.String(length=255), nullable=True),
    )
    op.create_index(op.f("ix_products_wb_nm_id"), "products", ["wb_nm_id"], unique=False)
    op.create_unique_constraint(
        "uq_products_tenant_wb_nm_id",
        "products",
        ["tenant_id", "wb_nm_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_products_tenant_wb_nm_id", "products", type_="unique")
    op.drop_index(op.f("ix_products_wb_nm_id"), table_name="products")
    op.drop_column("products", "wb_vendor_code")
    op.drop_column("products", "wb_nm_id")
