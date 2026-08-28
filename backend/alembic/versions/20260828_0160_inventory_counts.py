"""Add inventory count documents and movement linkage.

Revision ID: 20260828_0160
Revises: 20260828_0116
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0160"
down_revision: str | Sequence[str] | None = "20260828_0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_counts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["posted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "tenant_id",
        "warehouse_id",
        "seller_id",
        "created_at",
        "created_by_user_id",
        "posted_by_user_id",
    ):
        op.create_index(f"ix_inventory_counts_{column}", "inventory_counts", [column])

    op.create_table(
        "inventory_count_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("count_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("container_kind", sa.String(length=32), nullable=True),
        sa.Column("container_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("expected_quantity", sa.Integer(), nullable=False),
        sa.Column("actual_quantity", sa.Integer(), nullable=True),
        sa.Column("posted_delta", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["count_id"], ["inventory_counts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("count_id", "product_id", "storage_location_id"):
        op.create_index(
            f"ix_inventory_count_lines_{column}", "inventory_count_lines", [column]
        )
    op.create_index(
        "uq_inventory_count_line_scope",
        "inventory_count_lines",
        [
            "count_id",
            sa.text(
                "COALESCE(storage_location_id, '00000000-0000-0000-0000-000000000000')"
            ),
            sa.text("COALESCE(container_kind, '')"),
            sa.text("COALESCE(container_id, '00000000-0000-0000-0000-000000000000')"),
            "product_id",
        ],
        unique=True,
    )

    op.add_column(
        "inventory_movements",
        sa.Column("inventory_count_line_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_movements_inventory_count_line_id",
        "inventory_movements",
        "inventory_count_lines",
        ["inventory_count_line_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_inventory_movements_inventory_count_line_id",
        "inventory_movements",
        ["inventory_count_line_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_movements_inventory_count_line_id",
        table_name="inventory_movements",
    )
    op.drop_constraint(
        "fk_inventory_movements_inventory_count_line_id",
        "inventory_movements",
        type_="foreignkey",
    )
    op.drop_column("inventory_movements", "inventory_count_line_id")
    op.drop_table("inventory_count_lines")
    op.drop_table("inventory_counts")
