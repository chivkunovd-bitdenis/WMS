"""inventory balances and inbound posted_at

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_requests",
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["storage_location_id"], ["storage_locations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_location_id",
            "product_id",
            name="uq_inventory_balance_loc_product",
        ),
    )
    op.create_index(
        op.f("ix_inventory_balances_tenant_id"),
        "inventory_balances",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_inventory_balances_storage_location_id"),
        "inventory_balances",
        ["storage_location_id"],
    )
    op.create_index(
        op.f("ix_inventory_balances_product_id"),
        "inventory_balances",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inventory_balances_product_id"), table_name="inventory_balances")
    op.drop_index(
        op.f("ix_inventory_balances_storage_location_id"),
        table_name="inventory_balances",
    )
    op.drop_index(op.f("ix_inventory_balances_tenant_id"), table_name="inventory_balances")
    op.drop_table("inventory_balances")
    op.drop_column("inbound_intake_requests", "posted_at")
