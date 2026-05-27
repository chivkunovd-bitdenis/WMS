"""warehouse_boxes and marketplace unload box links

Revision ID: 0034
Revises: 0033
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "warehouse_boxes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("internal_barcode", sa.String(length=64), nullable=False),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["storage_location_id"], ["storage_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "internal_barcode",
            name="uq_warehouse_boxes_tenant_barcode",
        ),
    )
    op.create_index(
        "ix_warehouse_boxes_tenant_id", "warehouse_boxes", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_warehouse_boxes_warehouse_id",
        "warehouse_boxes",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        "ix_warehouse_boxes_storage_location_id",
        "warehouse_boxes",
        ["storage_location_id"],
        unique=False,
    )

    op.add_column(
        "marketplace_unload_boxes",
        sa.Column("warehouse_box_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_marketplace_unload_boxes_warehouse_box_id",
        "marketplace_unload_boxes",
        "warehouse_boxes",
        ["warehouse_box_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_marketplace_unload_boxes_warehouse_box_id",
        "marketplace_unload_boxes",
        ["warehouse_box_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketplace_unload_boxes_warehouse_box_id",
        table_name="marketplace_unload_boxes",
    )
    op.drop_constraint(
        "fk_marketplace_unload_boxes_warehouse_box_id",
        "marketplace_unload_boxes",
        type_="foreignkey",
    )
    op.drop_column("marketplace_unload_boxes", "warehouse_box_id")
    op.drop_table("warehouse_boxes")
