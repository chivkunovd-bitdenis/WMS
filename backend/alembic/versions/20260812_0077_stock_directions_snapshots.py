"""Stock directions and monthly stock snapshots.

Revision ID: 20260812_0077
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260812_0077"
down_revision = "20260809_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_directions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_fbs", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_directions_quantity_nonnegative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stock_directions_tenant_product",
        "stock_directions",
        ["tenant_id", "product_id"],
    )
    op.create_index(
        "ix_stock_directions_tenant_product_fbs",
        "stock_directions",
        ["tenant_id", "product_id", "is_fbs"],
    )
    op.create_index(op.f("ix_stock_directions_tenant_id"), "stock_directions", ["tenant_id"])
    op.create_index(op.f("ix_stock_directions_product_id"), "stock_directions", ["product_id"])

    op.create_table(
        "stock_monthly_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_month", sa.Date(), nullable=False),
        sa.Column("quantity_total", sa.Integer(), nullable=False),
        sa.Column("quantity_fbs", sa.Integer(), nullable=False),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False),
        sa.Column("quantity_free_fbo", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity_total >= 0", name="ck_stock_monthly_total_nonnegative"),
        sa.CheckConstraint("quantity_fbs >= 0", name="ck_stock_monthly_fbs_nonnegative"),
        sa.CheckConstraint("quantity_reserved >= 0", name="ck_stock_monthly_reserved_nonnegative"),
        sa.CheckConstraint("quantity_free_fbo >= 0", name="ck_stock_monthly_free_nonnegative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "product_id",
            "snapshot_month",
            name="uq_stock_monthly_snapshot_product_month",
        ),
    )
    op.create_index(
        "ix_stock_monthly_snapshots_tenant_month",
        "stock_monthly_snapshots",
        ["tenant_id", "snapshot_month"],
    )
    op.create_index(
        op.f("ix_stock_monthly_snapshots_tenant_id"),
        "stock_monthly_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_stock_monthly_snapshots_product_id"),
        "stock_monthly_snapshots",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_stock_monthly_snapshots_product_id"), table_name="stock_monthly_snapshots")
    op.drop_index(op.f("ix_stock_monthly_snapshots_tenant_id"), table_name="stock_monthly_snapshots")
    op.drop_index("ix_stock_monthly_snapshots_tenant_month", table_name="stock_monthly_snapshots")
    op.drop_table("stock_monthly_snapshots")
    op.drop_index(op.f("ix_stock_directions_product_id"), table_name="stock_directions")
    op.drop_index(op.f("ix_stock_directions_tenant_id"), table_name="stock_directions")
    op.drop_index("ix_stock_directions_tenant_product_fbs", table_name="stock_directions")
    op.drop_index("ix_stock_directions_tenant_product", table_name="stock_directions")
    op.drop_table("stock_directions")
