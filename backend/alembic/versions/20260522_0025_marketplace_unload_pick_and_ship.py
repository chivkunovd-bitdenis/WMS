"""Marketplace unload pick allocations and movement link."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_unload_pick_allocations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("marketplace_unload_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "storage_location_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("storage_locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "request_id",
            "product_id",
            "storage_location_id",
            name="uq_mp_unload_pick_req_product_loc",
        ),
    )
    op.create_index(
        "ix_marketplace_unload_pick_allocations_request_id",
        "marketplace_unload_pick_allocations",
        ["request_id"],
    )
    op.add_column(
        "inventory_movements",
        sa.Column(
            "marketplace_unload_request_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("marketplace_unload_requests.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_inventory_movements_marketplace_unload_request_id",
        "inventory_movements",
        ["marketplace_unload_request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_movements_marketplace_unload_request_id",
        table_name="inventory_movements",
    )
    op.drop_column("inventory_movements", "marketplace_unload_request_id")
    op.drop_index(
        "ix_marketplace_unload_pick_allocations_request_id",
        table_name="marketplace_unload_pick_allocations",
    )
    op.drop_table("marketplace_unload_pick_allocations")
