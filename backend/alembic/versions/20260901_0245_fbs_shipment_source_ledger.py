"""Add exact FBS shipment source and write-off audit fields.

Revision ID: 20260901_0245
Revises: 20260831_0244
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260901_0245"
down_revision: str | Sequence[str] | None = "20260831_0244"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("source_warehouse_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("container_kind", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("container_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("source_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column(
            "shortage_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column(
            "negative_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("wb_operation_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("written_off_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("written_off_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_fbs_shipment_reversal_source_warehouse",
        "fbs_shipment_reversal_ledger",
        "warehouses",
        ["source_warehouse_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_fbs_shipment_reversal_wb_operation",
        "fbs_shipment_reversal_ledger",
        "fbs_wb_operations",
        ["wb_operation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_fbs_shipment_reversal_written_off_by",
        "fbs_shipment_reversal_ledger",
        "users",
        ["written_off_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fbs_shipment_reversal_ledger_source_warehouse_id",
        "fbs_shipment_reversal_ledger",
        ["source_warehouse_id"],
    )
    op.create_index(
        "ix_fbs_shipment_reversal_ledger_container_id",
        "fbs_shipment_reversal_ledger",
        ["container_id"],
    )
    op.create_index(
        "ix_fbs_shipment_reversal_ledger_source_mode",
        "fbs_shipment_reversal_ledger",
        ["source_mode"],
    )
    op.create_index(
        "ix_fbs_shipment_reversal_ledger_wb_operation_id",
        "fbs_shipment_reversal_ledger",
        ["wb_operation_id"],
    )
    op.create_index(
        "ix_fbs_shipment_reversal_ledger_written_off_by_user_id",
        "fbs_shipment_reversal_ledger",
        ["written_off_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fbs_shipment_reversal_ledger_written_off_by_user_id",
        table_name="fbs_shipment_reversal_ledger",
    )
    op.drop_index(
        "ix_fbs_shipment_reversal_ledger_wb_operation_id",
        table_name="fbs_shipment_reversal_ledger",
    )
    op.drop_index(
        "ix_fbs_shipment_reversal_ledger_source_mode",
        table_name="fbs_shipment_reversal_ledger",
    )
    op.drop_index(
        "ix_fbs_shipment_reversal_ledger_container_id",
        table_name="fbs_shipment_reversal_ledger",
    )
    op.drop_index(
        "ix_fbs_shipment_reversal_ledger_source_warehouse_id",
        table_name="fbs_shipment_reversal_ledger",
    )
    op.drop_constraint(
        "fk_fbs_shipment_reversal_written_off_by",
        "fbs_shipment_reversal_ledger",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_fbs_shipment_reversal_wb_operation",
        "fbs_shipment_reversal_ledger",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_fbs_shipment_reversal_source_warehouse",
        "fbs_shipment_reversal_ledger",
        type_="foreignkey",
    )
    op.drop_column("fbs_shipment_reversal_ledger", "written_off_at")
    op.drop_column("fbs_shipment_reversal_ledger", "written_off_by_user_id")
    op.drop_column("fbs_shipment_reversal_ledger", "wb_operation_id")
    op.drop_column("fbs_shipment_reversal_ledger", "negative_quantity")
    op.drop_column("fbs_shipment_reversal_ledger", "shortage_quantity")
    op.drop_column("fbs_shipment_reversal_ledger", "source_mode")
    op.drop_column("fbs_shipment_reversal_ledger", "container_id")
    op.drop_column("fbs_shipment_reversal_ledger", "container_kind")
    op.drop_column("fbs_shipment_reversal_ledger", "source_warehouse_id")
