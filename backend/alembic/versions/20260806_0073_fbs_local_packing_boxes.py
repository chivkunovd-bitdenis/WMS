"""FBS local physical packing boxes and explicit operator finish.

Revision ID: 20260806_0073
Revises: 20260804_0072
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0073"
down_revision: str | Sequence[str] | None = "20260804_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fbs_supplies", sa.Column("operator_finished_at", sa.DateTime(timezone=True)))
    op.add_column("fbs_supplies", sa.Column("operator_finished_by_user_id", sa.Uuid(as_uuid=True)))
    op.add_column("fbs_supplies", sa.Column("operator_finish_idempotency_key", sa.String(128)))
    op.create_foreign_key(
        "fk_fbs_supplies_operator_finished_by_user_id",
        "fbs_supplies",
        "users",
        ["operator_finished_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "fbs_packing_boxes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("supply_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_box_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("box_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), server_default="open", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supply_id"], ["fbs_supplies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_box_id"], ["warehouse_boxes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("supply_id", "box_number", name="uq_fbs_packing_boxes_supply_number"),
        sa.UniqueConstraint("warehouse_box_id", name="uq_fbs_packing_boxes_warehouse_box"),
    )
    op.create_index("ix_fbs_packing_boxes_tenant_id", "fbs_packing_boxes", ["tenant_id"])
    op.create_index("ix_fbs_packing_boxes_supply_id", "fbs_packing_boxes", ["supply_id"])
    op.create_index(
        "ix_fbs_packing_boxes_warehouse_box_id",
        "fbs_packing_boxes",
        ["warehouse_box_id"],
    )
    op.create_table(
        "fbs_packing_box_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("box_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("fbs_order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(as_uuid=True)),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["box_id"], ["fbs_packing_boxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fbs_order_id"], ["fbs_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("fbs_order_id", name="uq_fbs_packing_box_items_order"),
    )
    op.create_index("ix_fbs_packing_box_items_tenant_id", "fbs_packing_box_items", ["tenant_id"])
    op.create_index("ix_fbs_packing_box_items_box_id", "fbs_packing_box_items", ["box_id"])
    op.create_index(
        "ix_fbs_packing_box_items_fbs_order_id",
        "fbs_packing_box_items",
        ["fbs_order_id"],
    )


def downgrade() -> None:
    op.drop_table("fbs_packing_box_items")
    op.drop_table("fbs_packing_boxes")
    op.drop_constraint(
        "fk_fbs_supplies_operator_finished_by_user_id",
        "fbs_supplies",
        type_="foreignkey",
    )
    op.drop_column("fbs_supplies", "operator_finish_idempotency_key")
    op.drop_column("fbs_supplies", "operator_finished_by_user_id")
    op.drop_column("fbs_supplies", "operator_finished_at")
