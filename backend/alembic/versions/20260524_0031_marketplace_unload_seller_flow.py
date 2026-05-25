"""marketplace unload seller plan flow: dates, ff_modified, reservations

Revision ID: 0031
Revises: 0030
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marketplace_unload_requests",
        sa.Column("planned_shipment_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "marketplace_unload_requests",
        sa.Column(
            "ff_modified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "marketplace_unload_reservations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "marketplace_unload_line_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("marketplace_unload_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "marketplace_unload_line_id",
            name="uq_marketplace_unload_reservation_line",
        ),
    )
    op.create_index(
        "ix_marketplace_unload_reservations_tenant_id",
        "marketplace_unload_reservations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_marketplace_unload_reservations_product_id",
        "marketplace_unload_reservations",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketplace_unload_reservations_product_id",
        table_name="marketplace_unload_reservations",
    )
    op.drop_index(
        "ix_marketplace_unload_reservations_tenant_id",
        table_name="marketplace_unload_reservations",
    )
    op.drop_table("marketplace_unload_reservations")
    op.drop_column("marketplace_unload_requests", "ff_modified")
    op.drop_column("marketplace_unload_requests", "planned_shipment_date")
