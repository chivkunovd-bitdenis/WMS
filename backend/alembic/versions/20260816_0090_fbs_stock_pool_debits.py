"""Add fbs_stock_pool_debits table (idempotency ledger for order-driven pool debits).

Revision ID: 20260816_0090
Revises: 20260816_0089
Create Date: 2026-08-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260816_0090"
down_revision: Union[str, None] = "20260816_0089"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fbs_stock_pool_debits",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pool_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("fbs_binding_stock_pools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("fbs_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity_debited", sa.Integer(), nullable=False),
        sa.Column(
            "quantity_shortfall", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("order_id", name="uq_fbs_stock_pool_debits_order"),
    )
    op.create_index(
        "ix_fbs_stock_pool_debits_tenant_id",
        "fbs_stock_pool_debits",
        ["tenant_id"],
    )
    op.create_index(
        "ix_fbs_stock_pool_debits_pool_id",
        "fbs_stock_pool_debits",
        ["pool_id"],
    )


def downgrade() -> None:
    op.drop_table("fbs_stock_pool_debits")
