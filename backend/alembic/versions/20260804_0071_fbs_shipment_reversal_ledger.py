"""FBS shipment reversal ledger.

Revision ID: 20260804_0071
Revises: 20260804_0070
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_0071"
down_revision = "20260804_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fbs_shipment_reversal_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("fbs_order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("storage_location_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_movement_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fbs_order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reversal_movement_id"], ["inventory_movements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fbs_order_id", name="uq_fbs_shipment_reversal_order"),
    )
    op.create_index("ix_fbs_shipment_reversal_ledger_tenant_id", "fbs_shipment_reversal_ledger", ["tenant_id"])
    op.create_index("ix_fbs_shipment_reversal_ledger_fbs_order_id", "fbs_shipment_reversal_ledger", ["fbs_order_id"])


def downgrade() -> None:
    op.drop_index("ix_fbs_shipment_reversal_ledger_fbs_order_id", table_name="fbs_shipment_reversal_ledger")
    op.drop_index("ix_fbs_shipment_reversal_ledger_tenant_id", table_name="fbs_shipment_reversal_ledger")
    op.drop_table("fbs_shipment_reversal_ledger")
