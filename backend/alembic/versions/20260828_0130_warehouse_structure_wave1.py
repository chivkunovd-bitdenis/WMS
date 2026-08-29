"""Warehouse structure wave 1: pallets, containers, cargo-place contents.

Revision ID: 20260828_0130
Revises: 20260828_0116
Create Date: 2026-08-28

The upgrade does not remove tables or columns.  The former two-column balance
uniqueness constraint is replaced only because it cannot represent the same
product in two physical containers at one location.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0130"
down_revision: str | Sequence[str] | None = "20260828_0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.create_table(
        "pallets",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=False),
        sa.Column("free_text", sa.Text(), nullable=True),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("disbanded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["storage_location_id"],
            ["storage_locations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_pallets_tenant_code"),
        sa.UniqueConstraint(
            "tenant_id", "barcode", name="uq_pallets_tenant_barcode"
        ),
    )
    op.create_index("ix_pallets_tenant_id", "pallets", ["tenant_id"])
    op.create_index("ix_pallets_warehouse_id", "pallets", ["warehouse_id"])
    op.create_index(
        "ix_pallets_storage_location_id", "pallets", ["storage_location_id"]
    )

    op.add_column("inbound_intake_requests", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column("inbound_intake_boxes", sa.Column("free_text", sa.Text(), nullable=True))
    op.add_column(
        "inbound_intake_boxes",
        sa.Column("pallet_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inbound_intake_boxes_pallet_id",
        "inbound_intake_boxes",
        "pallets",
        ["pallet_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_inbound_intake_boxes_pallet_id",
        "inbound_intake_boxes",
        ["pallet_id"],
    )

    op.add_column(
        "inbound_intake_cargo_places", sa.Column("free_text", sa.Text(), nullable=True)
    )
    op.add_column(
        "inbound_intake_cargo_places",
        sa.Column("pallet_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inbound_intake_cargo_places_pallet_id",
        "inbound_intake_cargo_places",
        "pallets",
        ["pallet_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_inbound_intake_cargo_places_pallet_id",
        "inbound_intake_cargo_places",
        ["pallet_id"],
    )

    op.add_column(
        "warehouse_boxes", sa.Column("pallet_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_warehouse_boxes_pallet_id",
        "warehouse_boxes",
        "pallets",
        ["pallet_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_warehouse_boxes_pallet_id", "warehouse_boxes", ["pallet_id"])

    op.create_table(
        "inbound_intake_cargo_place_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("cargo_place_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("posted_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity >= 0", name="ck_inbound_cargo_place_line_quantity_nonnegative"
        ),
        sa.CheckConstraint(
            "posted_qty >= 0", name="ck_inbound_cargo_place_line_posted_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["cargo_place_id"],
            ["inbound_intake_cargo_places.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cargo_place_id",
            "product_id",
            name="uq_inbound_intake_cargo_place_line_place_product",
        ),
    )
    op.create_index(
        "ix_inbound_intake_cargo_place_lines_tenant_id",
        "inbound_intake_cargo_place_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_inbound_intake_cargo_place_lines_cargo_place_id",
        "inbound_intake_cargo_place_lines",
        ["cargo_place_id"],
    )
    op.create_index(
        "ix_inbound_intake_cargo_place_lines_product_id",
        "inbound_intake_cargo_place_lines",
        ["product_id"],
    )

    op.add_column(
        "inventory_balances", sa.Column("container_kind", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "inventory_balances", sa.Column("container_id", sa.Uuid(as_uuid=True), nullable=True)
    )
    op.create_index(
        "ix_inventory_balances_container_kind",
        "inventory_balances",
        ["container_kind"],
    )
    op.create_index(
        "ix_inventory_balances_container_id",
        "inventory_balances",
        ["container_id"],
    )
    op.create_check_constraint(
        "ck_inventory_balance_container_pair",
        "inventory_balances",
        "(container_kind IS NULL AND container_id IS NULL) OR "
        "(container_kind IS NOT NULL AND container_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_inventory_balance_container_kind",
        "inventory_balances",
        "container_kind IS NULL OR container_kind IN ('pallet', 'box', 'cargo_place')",
    )
    # Эти проверки намеренно не создаём: минус в остатке — законный след
    # подтверждённой доставки FBS, и на бою уже есть 115 таких строк.
    op.create_index(
        "uq_inventory_balance_loc_product_container",
        "inventory_balances",
        [
            "storage_location_id",
            "product_id",
            sa.text(f"coalesce(container_id, '{_NIL_UUID}')"),
        ],
        unique=True,
    )
    op.drop_constraint(
        "uq_inventory_balance_loc_product",
        "inventory_balances",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_inventory_balance_loc_product",
        "inventory_balances",
        ["storage_location_id", "product_id"],
    )
    op.drop_index(
        "uq_inventory_balance_loc_product_container", table_name="inventory_balances"
    )
    op.drop_constraint(
        "ck_inventory_balance_container_kind",
        "inventory_balances",
        type_="check",
    )
    op.drop_constraint(
        "ck_inventory_balance_container_pair",
        "inventory_balances",
        type_="check",
    )
    op.drop_index("ix_inventory_balances_container_id", table_name="inventory_balances")
    op.drop_index("ix_inventory_balances_container_kind", table_name="inventory_balances")
    op.drop_column("inventory_balances", "container_id")
    op.drop_column("inventory_balances", "container_kind")

    op.drop_index(
        "ix_inbound_intake_cargo_place_lines_product_id",
        table_name="inbound_intake_cargo_place_lines",
    )
    op.drop_index(
        "ix_inbound_intake_cargo_place_lines_cargo_place_id",
        table_name="inbound_intake_cargo_place_lines",
    )
    op.drop_index(
        "ix_inbound_intake_cargo_place_lines_tenant_id",
        table_name="inbound_intake_cargo_place_lines",
    )
    op.drop_table("inbound_intake_cargo_place_lines")

    op.drop_index("ix_warehouse_boxes_pallet_id", table_name="warehouse_boxes")
    op.drop_constraint(
        "fk_warehouse_boxes_pallet_id", "warehouse_boxes", type_="foreignkey"
    )
    op.drop_column("warehouse_boxes", "pallet_id")

    op.drop_index(
        "ix_inbound_intake_cargo_places_pallet_id",
        table_name="inbound_intake_cargo_places",
    )
    op.drop_constraint(
        "fk_inbound_intake_cargo_places_pallet_id",
        "inbound_intake_cargo_places",
        type_="foreignkey",
    )
    op.drop_column("inbound_intake_cargo_places", "pallet_id")
    op.drop_column("inbound_intake_cargo_places", "free_text")

    op.drop_index(
        "ix_inbound_intake_boxes_pallet_id", table_name="inbound_intake_boxes"
    )
    op.drop_constraint(
        "fk_inbound_intake_boxes_pallet_id",
        "inbound_intake_boxes",
        type_="foreignkey",
    )
    op.drop_column("inbound_intake_boxes", "pallet_id")
    op.drop_column("inbound_intake_boxes", "free_text")
    op.drop_column("inbound_intake_requests", "comment")

    op.drop_index("ix_pallets_storage_location_id", table_name="pallets")
    op.drop_index("ix_pallets_warehouse_id", table_name="pallets")
    op.drop_index("ix_pallets_tenant_id", table_name="pallets")
    op.drop_table("pallets")
