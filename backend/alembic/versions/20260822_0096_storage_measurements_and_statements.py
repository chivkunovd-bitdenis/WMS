"""Add immutable storage measurements and monthly statements."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260822_0096"
down_revision: str | Sequence[str] | None = "20260822_0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_measurements",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "seller_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("sellers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dimension_event_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("product_dimension_events.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "movement_start_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "movement_end_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("inventory_movements.id", ondelete="RESTRICT"),
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_storage_measurements_period_end_after_start",
        ),
        sa.CheckConstraint(
            "quantity_days >= 0",
            name="ck_storage_measurements_quantity_days_nonnegative",
        ),
        sa.CheckConstraint(
            "liter_days >= 0",
            name="ck_storage_measurements_liter_days_nonnegative",
        ),
        sa.Column("quantity_days", sa.Numeric(18, 6), nullable=False),
        sa.Column("liter_days", sa.Numeric(24, 6), nullable=False),
        sa.Column("status", sa.String(32), server_default="calculated", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "warehouse_id",
            "product_id",
            "period_start",
            name="uq_storage_measurements_tenant_seller_warehouse_product_period",
        ),
    )
    for name, cols in (
        ("tenant_id", ["tenant_id"]),
        ("seller_id", ["seller_id"]),
        ("warehouse_id", ["warehouse_id"]),
        ("product_id", ["product_id"]),
        ("scope_period", ["tenant_id", "seller_id", "warehouse_id", "period_start", "period_end"]),
    ):
        op.create_index(f"ix_storage_measurements_{name}", "storage_measurements", cols)
    op.create_table(
        "storage_statements",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "seller_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("sellers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_storage_statements_period_end_after_start",
        ),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("document_number", sa.String(64)),
        sa.Column("fixed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "warehouse_id",
            "period_start",
            name="uq_storage_statements_tenant_seller_warehouse_period",
        ),
    )
    op.create_index("ix_storage_statements_tenant_id", "storage_statements", ["tenant_id"])
    op.create_index(
        "ix_storage_statements_scope_status",
        "storage_statements",
        ["tenant_id", "seller_id", "warehouse_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_storage_statements_scope_status", table_name="storage_statements")
    op.drop_index("ix_storage_statements_tenant_id", table_name="storage_statements")
    op.drop_table("storage_statements")
    for name in ("scope_period", "product_id", "warehouse_id", "seller_id", "tenant_id"):
        op.drop_index(f"ix_storage_measurements_{name}", table_name="storage_measurements")
    op.drop_table("storage_measurements")
