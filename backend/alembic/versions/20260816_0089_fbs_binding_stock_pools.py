"""Add fbs_binding_stock_pools table.

Revision ID: 20260816_0089
Revises: 20260816_0088
Create Date: 2026-08-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260816_0089"
down_revision: Union[str, None] = "20260816_0088"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fbs_binding_stock_pools",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "binding_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("fbs_warehouse_bindings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_fbs_binding_stock_pools_quantity_non_negative",
        ),
        sa.UniqueConstraint(
            "binding_id",
            "product_id",
            name="uq_fbs_binding_stock_pools_binding_product",
        ),
    )
    op.create_index(
        "ix_fbs_binding_stock_pools_tenant_id",
        "fbs_binding_stock_pools",
        ["tenant_id"],
    )
    op.create_index(
        "ix_fbs_binding_stock_pools_binding_id",
        "fbs_binding_stock_pools",
        ["binding_id"],
    )
    op.create_index(
        "ix_fbs_binding_stock_pools_product_id",
        "fbs_binding_stock_pools",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_table("fbs_binding_stock_pools")
