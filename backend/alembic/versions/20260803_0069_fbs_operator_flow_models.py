"""FBS operator flow models: picks, print assets, WB ops, packaging fulfillments.

Revision ID: 20260803_0069
Revises: 20260802_0068
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0069"
down_revision: str | Sequence[str] | None = "20260802_0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fbs_print_assets",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="requesting",
            nullable=False,
        ),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("storage_path", sa.String(length=512), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("wb_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fbs_order_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("fbs_supply_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("fbs_trbx_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("print_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["fbs_order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fbs_supply_id"], ["fbs_supplies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fbs_trbx_id"], ["fbs_trbxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fbs_print_assets_tenant_id", "fbs_print_assets", ["tenant_id"])
    op.create_index("ix_fbs_print_assets_seller_id", "fbs_print_assets", ["seller_id"])
    op.create_index("ix_fbs_print_assets_fbs_order_id", "fbs_print_assets", ["fbs_order_id"])
    op.create_index("ix_fbs_print_assets_fbs_supply_id", "fbs_print_assets", ["fbs_supply_id"])
    op.create_index("ix_fbs_print_assets_fbs_trbx_id", "fbs_print_assets", ["fbs_trbx_id"])
    op.create_index(
        "ix_fbs_print_assets_tenant_seller_kind_status",
        "fbs_print_assets",
        ["tenant_id", "seller_id", "kind", "status"],
    )
    op.create_index(
        "uq_fbs_print_assets_ready_order_sticker",
        "fbs_print_assets",
        ["fbs_order_id", "kind"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ready' AND kind = 'order_sticker' AND fbs_order_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_fbs_print_assets_ready_supply_qr",
        "fbs_print_assets",
        ["fbs_supply_id", "kind"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ready' AND kind = 'supply_qr' AND fbs_supply_id IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_fbs_print_assets_ready_cargo_qr",
        "fbs_print_assets",
        ["fbs_trbx_id", "kind"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'ready' AND kind = 'cargo_place_qr' AND fbs_trbx_id IS NOT NULL"
        ),
    )

    op.create_table(
        "fbs_order_picks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("fbs_order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("fbs_supply_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_storage_location_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sorting_storage_location_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scanned_product_barcode", sa.String(length=64), nullable=True),
        sa.Column("picked_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inventory_movement_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("scan_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fbs_order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fbs_supply_id"], ["fbs_supplies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inventory_movement_id"], ["inventory_movements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["picked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sorting_storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fbs_supply_id",
            "scan_idempotency_key",
            name="uq_fbs_order_picks_supply_scan_idempotency",
        ),
    )
    op.create_index("ix_fbs_order_picks_tenant_id", "fbs_order_picks", ["tenant_id"])
    op.create_index("ix_fbs_order_picks_fbs_order_id", "fbs_order_picks", ["fbs_order_id"])
    op.create_index("ix_fbs_order_picks_fbs_supply_id", "fbs_order_picks", ["fbs_supply_id"])
    op.create_index(
        "ix_fbs_order_picks_tenant_supply",
        "fbs_order_picks",
        ["tenant_id", "fbs_supply_id"],
    )
    op.create_index(
        "uq_fbs_order_picks_active_order",
        "fbs_order_picks",
        ["fbs_order_id"],
        unique=True,
        postgresql_where=sa.text("undone_at IS NULL"),
    )

    op.create_table(
        "fbs_order_pick_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("pick_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("source_storage_location_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sorting_storage_location_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("inventory_movement_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inventory_movement_id"], ["inventory_movements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pick_id"], ["fbs_order_picks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["sorting_storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_storage_location_id"], ["storage_locations.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fbs_order_pick_events_pick_id", "fbs_order_pick_events", ["pick_id"])
    op.create_index(
        "uq_fbs_order_pick_events_undo_idempotency",
        "fbs_order_pick_events",
        ["pick_id", "event_type", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "fbs_packaging_fulfillments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("fbs_order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("packaging_task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("packaging_task_line_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("fulfilled_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inventory_movement_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("pack_idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fbs_order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fulfilled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inventory_movement_id"], ["inventory_movements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["packaging_task_id"], ["packaging_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["packaging_task_line_id"], ["packaging_task_lines.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "packaging_task_id",
            "pack_idempotency_key",
            name="uq_fbs_packaging_fulfillments_task_idempotency",
        ),
    )
    op.create_index(
        "ix_fbs_packaging_fulfillments_tenant_id", "fbs_packaging_fulfillments", ["tenant_id"]
    )
    op.create_index(
        "ix_fbs_packaging_fulfillments_fbs_order_id",
        "fbs_packaging_fulfillments",
        ["fbs_order_id"],
    )
    op.create_index(
        "ix_fbs_packaging_fulfillments_packaging_task_id",
        "fbs_packaging_fulfillments",
        ["packaging_task_id"],
    )
    op.create_index(
        "ix_fbs_packaging_fulfillments_packaging_task_line_id",
        "fbs_packaging_fulfillments",
        ["packaging_task_line_id"],
    )
    op.create_index(
        "uq_fbs_packaging_fulfillments_active_order",
        "fbs_packaging_fulfillments",
        ["fbs_order_id"],
        unique=True,
        postgresql_where=sa.text("undone_at IS NULL"),
    )

    op.create_table(
        "fbs_wb_operations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("operation_kind", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=True),
        sa.Column("wb_object_id", sa.String(length=128), nullable=True),
        sa.Column("wb_object_kind", sa.String(length=32), nullable=True),
        sa.Column("local_entity_type", sa.String(length=32), nullable=True),
        sa.Column("local_entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "state",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_context_json", sa.JSON(), nullable=True),
        sa.Column("request_summary_json", sa.JSON(), nullable=True),
        sa.Column("response_summary_json", sa.JSON(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "seller_id",
            "operation_kind",
            "idempotency_key",
            name="uq_fbs_wb_operations_seller_kind_idempotency",
        ),
    )
    op.create_index("ix_fbs_wb_operations_tenant_id", "fbs_wb_operations", ["tenant_id"])
    op.create_index("ix_fbs_wb_operations_seller_id", "fbs_wb_operations", ["seller_id"])
    op.create_index(
        "ix_fbs_wb_operations_tenant_seller_state",
        "fbs_wb_operations",
        ["tenant_id", "seller_id", "state"],
    )
    op.create_index(
        "ix_fbs_wb_operations_local_entity",
        "fbs_wb_operations",
        ["local_entity_type", "local_entity_id"],
    )

    # fbs_orders — add nullable first, backfill, then NOT NULL
    op.add_column(
        "fbs_orders",
        sa.Column("pick_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fbs_orders",
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fbs_orders",
        sa.Column("pack_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fbs_orders",
        sa.Column("packed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fbs_orders",
        sa.Column("sticker_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fbs_orders",
        sa.Column("sticker_applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("fbs_orders", sa.Column("required_meta_json", sa.JSON(), nullable=True))
    op.add_column("fbs_orders", sa.Column("optional_meta_json", sa.JSON(), nullable=True))
    op.add_column("fbs_orders", sa.Column("meta_details_json", sa.JSON(), nullable=True))
    op.add_column(
        "fbs_orders",
        sa.Column("metadata_delivery_allowed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "fbs_orders",
        sa.Column("metadata_last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fbs_orders",
        sa.Column("last_wb_sync_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(sa.text("UPDATE fbs_orders SET pick_status = 'pending' WHERE pick_status IS NULL"))
    op.execute(sa.text("UPDATE fbs_orders SET pack_status = 'pending' WHERE pack_status IS NULL"))
    op.execute(
        sa.text(
            "UPDATE fbs_orders SET sticker_status = 'ready' "
            "WHERE sticker_status IS NULL AND sticker_file IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE fbs_orders SET sticker_status = 'not_requested' "
            "WHERE sticker_status IS NULL"
        )
    )

    op.alter_column("fbs_orders", "pick_status", nullable=False, server_default="pending")
    op.alter_column("fbs_orders", "pack_status", nullable=False, server_default="pending")
    op.alter_column(
        "fbs_orders", "sticker_status", nullable=False, server_default="not_requested"
    )

    op.create_index(
        "ix_fbs_orders_tenant_seller_status_deadline",
        "fbs_orders",
        ["tenant_id", "seller_id", "status", "deadline_at"],
    )
    op.create_index(
        "ix_fbs_orders_tenant_seller_supply",
        "fbs_orders",
        ["tenant_id", "seller_id", "supply_id"],
    )

    op.add_column(
        "fbs_order_markings",
        sa.Column("meta_status", sa.String(length=32), nullable=True),
    )
    op.add_column("fbs_order_markings", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column(
        "fbs_order_markings", sa.Column("meta_details_json", sa.JSON(), nullable=True)
    )

    op.execute(
        sa.text(
            "UPDATE fbs_order_markings SET meta_status = 'accepted' "
            "WHERE meta_status IS NULL AND check_status = 'ok'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE fbs_order_markings SET meta_status = 'rejected' "
            "WHERE meta_status IS NULL AND check_status = 'error'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE fbs_order_markings SET meta_status = 'missing' "
            "WHERE meta_status IS NULL AND check_status = 'new'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE fbs_order_markings SET meta_status = 'unknown' "
            "WHERE meta_status IS NULL"
        )
    )
    op.alter_column(
        "fbs_order_markings",
        "meta_status",
        nullable=False,
        server_default="missing",
    )

    op.add_column(
        "fbs_supplies",
        sa.Column("planned_destination_office_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "fbs_supplies",
        sa.Column("planned_destination_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "fbs_supplies",
        sa.Column("planned_destination_zone", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "fbs_supplies",
        sa.Column("last_wb_sync_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fbs_supplies",
        sa.Column("barcode_asset_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_supplies_barcode_asset_id",
        "fbs_supplies",
        "fbs_print_assets",
        ["barcode_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fbs_supplies_barcode_asset_id", "fbs_supplies", ["barcode_asset_id"]
    )

    op.add_column(
        "fbs_trbxes",
        sa.Column("qr_asset_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fbs_trbxes",
        sa.Column("qr_applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fbs_trbxes",
        sa.Column("qr_applied_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_trbxes_qr_asset_id",
        "fbs_trbxes",
        "fbs_print_assets",
        ["qr_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_fbs_trbxes_qr_applied_by_user_id",
        "fbs_trbxes",
        "users",
        ["qr_applied_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_fbs_trbxes_qr_asset_id", "fbs_trbxes", ["qr_asset_id"])


def downgrade() -> None:
    op.drop_index("ix_fbs_trbxes_qr_asset_id", table_name="fbs_trbxes")
    op.drop_constraint("fk_fbs_trbxes_qr_applied_by_user_id", "fbs_trbxes", type_="foreignkey")
    op.drop_constraint("fk_fbs_trbxes_qr_asset_id", "fbs_trbxes", type_="foreignkey")
    op.drop_column("fbs_trbxes", "qr_applied_by_user_id")
    op.drop_column("fbs_trbxes", "qr_applied_at")
    op.drop_column("fbs_trbxes", "qr_asset_id")

    op.drop_index("ix_fbs_supplies_barcode_asset_id", table_name="fbs_supplies")
    op.drop_constraint("fk_fbs_supplies_barcode_asset_id", "fbs_supplies", type_="foreignkey")
    op.drop_column("fbs_supplies", "barcode_asset_id")
    op.drop_column("fbs_supplies", "last_wb_sync_at")
    op.drop_column("fbs_supplies", "planned_destination_zone")
    op.drop_column("fbs_supplies", "planned_destination_name")
    op.drop_column("fbs_supplies", "planned_destination_office_id")

    op.drop_column("fbs_order_markings", "meta_details_json")
    op.drop_column("fbs_order_markings", "reason")
    op.drop_column("fbs_order_markings", "meta_status")

    op.drop_index("ix_fbs_orders_tenant_seller_supply", table_name="fbs_orders")
    op.drop_index("ix_fbs_orders_tenant_seller_status_deadline", table_name="fbs_orders")
    op.drop_column("fbs_orders", "last_wb_sync_at")
    op.drop_column("fbs_orders", "metadata_last_checked_at")
    op.drop_column("fbs_orders", "metadata_delivery_allowed")
    op.drop_column("fbs_orders", "meta_details_json")
    op.drop_column("fbs_orders", "optional_meta_json")
    op.drop_column("fbs_orders", "required_meta_json")
    op.drop_column("fbs_orders", "sticker_applied_at")
    op.drop_column("fbs_orders", "sticker_status")
    op.drop_column("fbs_orders", "packed_at")
    op.drop_column("fbs_orders", "pack_status")
    op.drop_column("fbs_orders", "picked_at")
    op.drop_column("fbs_orders", "pick_status")

    op.drop_index("ix_fbs_wb_operations_local_entity", table_name="fbs_wb_operations")
    op.drop_index("ix_fbs_wb_operations_tenant_seller_state", table_name="fbs_wb_operations")
    op.drop_index("ix_fbs_wb_operations_seller_id", table_name="fbs_wb_operations")
    op.drop_index("ix_fbs_wb_operations_tenant_id", table_name="fbs_wb_operations")
    op.drop_table("fbs_wb_operations")

    op.drop_index(
        "uq_fbs_packaging_fulfillments_active_order", table_name="fbs_packaging_fulfillments"
    )
    op.drop_index(
        "ix_fbs_packaging_fulfillments_packaging_task_line_id",
        table_name="fbs_packaging_fulfillments",
    )
    op.drop_index(
        "ix_fbs_packaging_fulfillments_packaging_task_id",
        table_name="fbs_packaging_fulfillments",
    )
    op.drop_index(
        "ix_fbs_packaging_fulfillments_fbs_order_id", table_name="fbs_packaging_fulfillments"
    )
    op.drop_index(
        "ix_fbs_packaging_fulfillments_tenant_id", table_name="fbs_packaging_fulfillments"
    )
    op.drop_table("fbs_packaging_fulfillments")

    op.drop_index("uq_fbs_order_pick_events_undo_idempotency", table_name="fbs_order_pick_events")
    op.drop_index("ix_fbs_order_pick_events_pick_id", table_name="fbs_order_pick_events")
    op.drop_table("fbs_order_pick_events")

    op.drop_index("uq_fbs_order_picks_active_order", table_name="fbs_order_picks")
    op.drop_index("ix_fbs_order_picks_tenant_supply", table_name="fbs_order_picks")
    op.drop_index("ix_fbs_order_picks_fbs_supply_id", table_name="fbs_order_picks")
    op.drop_index("ix_fbs_order_picks_fbs_order_id", table_name="fbs_order_picks")
    op.drop_index("ix_fbs_order_picks_tenant_id", table_name="fbs_order_picks")
    op.drop_table("fbs_order_picks")

    op.drop_index("uq_fbs_print_assets_ready_cargo_qr", table_name="fbs_print_assets")
    op.drop_index("uq_fbs_print_assets_ready_supply_qr", table_name="fbs_print_assets")
    op.drop_index("uq_fbs_print_assets_ready_order_sticker", table_name="fbs_print_assets")
    op.drop_index(
        "ix_fbs_print_assets_tenant_seller_kind_status", table_name="fbs_print_assets"
    )
    op.drop_index("ix_fbs_print_assets_fbs_trbx_id", table_name="fbs_print_assets")
    op.drop_index("ix_fbs_print_assets_fbs_supply_id", table_name="fbs_print_assets")
    op.drop_index("ix_fbs_print_assets_fbs_order_id", table_name="fbs_print_assets")
    op.drop_index("ix_fbs_print_assets_seller_id", table_name="fbs_print_assets")
    op.drop_index("ix_fbs_print_assets_tenant_id", table_name="fbs_print_assets")
    op.drop_table("fbs_print_assets")
