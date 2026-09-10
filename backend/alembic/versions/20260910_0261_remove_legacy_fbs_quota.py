"""WMS-338 remove the retired order-debit ledger and FBS direction flag.

The ledger is obsolete, not warehouse movements or operator caps. Take the
normal database backup before deployment; downgrade restores schema only.
Existing true FBS directions require an explicit data decision, never silently
turn them into ordinary reservations. Production read-only preflight on
2026-09-10 found zero such directions and 1740 obsolete ledger rows.
"""

import sqlalchemy as sa

from alembic import op

revision = "20260910_0261"
down_revision = "20260908_0257"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM stock_directions WHERE is_fbs")):
        raise RuntimeError("WMS-338: legacy FBS directions need an explicit data decision")
    op.drop_table("fbs_stock_pool_debits")
    op.drop_index("ix_stock_directions_tenant_product_fbs", table_name="stock_directions")
    op.drop_column("stock_directions", "is_fbs")


def downgrade() -> None:
    op.add_column(
        "stock_directions",
        sa.Column("is_fbs", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_stock_directions_tenant_product_fbs",
        "stock_directions",
        ["tenant_id", "product_id", "is_fbs"],
    )
    op.create_table(
        "fbs_stock_pool_debits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "pool_id",
            sa.Uuid(),
            sa.ForeignKey("fbs_binding_stock_pools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("fbs_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity_debited", sa.Integer(), nullable=False),
        sa.Column("quantity_shortfall", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("order_id", name="uq_fbs_stock_pool_debits_order"),
    )
    op.create_index("ix_fbs_stock_pool_debits_tenant_id", "fbs_stock_pool_debits", ["tenant_id"])
    op.create_index("ix_fbs_stock_pool_debits_pool_id", "fbs_stock_pool_debits", ["pool_id"])
