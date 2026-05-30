"""packaging tasks + inventory unpacked/packed split

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_balances",
        sa.Column("quantity_unpacked", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_balances",
        sa.Column("quantity_packed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        sa.text(
            "UPDATE inventory_balances "
            "SET quantity_unpacked = quantity, quantity_packed = 0"
        )
    )
    op.alter_column("inventory_balances", "quantity_unpacked", server_default=None)
    op.alter_column("inventory_balances", "quantity_packed", server_default=None)

    op.add_column(
        "products",
        sa.Column("packaging_instructions", sa.Text(), nullable=True),
    )

    op.create_table(
        "packaging_tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("marketplace_unload_request_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("inbound_intake_request_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["inbound_intake_request_id"], ["inbound_intake_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["marketplace_unload_request_id"], ["marketplace_unload_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "marketplace_unload_request_id",
            name="uq_packaging_task_marketplace_unload",
        ),
    )
    op.create_index("ix_packaging_tasks_tenant_id", "packaging_tasks", ["tenant_id"])
    op.create_index(
        "ix_packaging_tasks_marketplace_unload_request_id",
        "packaging_tasks",
        ["marketplace_unload_request_id"],
    )

    op.create_table(
        "packaging_task_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("qty_total", sa.Integer(), nullable=False),
        sa.Column("qty_suggested_packed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qty_confirmed_packed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qty_packed_in_task", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("marketplace_unload_line_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["marketplace_unload_line_id"], ["marketplace_unload_lines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["storage_location_id"], ["storage_locations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["packaging_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "product_id",
            "storage_location_id",
            name="uq_packaging_task_line_task_product_loc",
        ),
    )
    op.create_index("ix_packaging_task_lines_task_id", "packaging_task_lines", ["task_id"])


def downgrade() -> None:
    op.drop_table("packaging_task_lines")
    op.drop_table("packaging_tasks")
    op.drop_column("products", "packaging_instructions")
    op.drop_column("inventory_balances", "quantity_packed")
    op.drop_column("inventory_balances", "quantity_unpacked")
