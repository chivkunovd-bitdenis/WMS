"""FBS PVZ trbx (cargo places) and order.trbx_id FK.

Revision ID: 20260730_0066
Revises: 20260730_0065
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260730_0066"
down_revision = "20260730_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fbs_trbxes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("supply_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("wb_trbx_id", sa.String(length=64), nullable=False),
        sa.Column("packaging_box_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("length_mm", sa.Integer(), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("weight_g", sa.Integer(), nullable=True),
        sa.Column("sticker_file", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["supply_id"], ["fbs_supplies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fbs_trbxes_supply_id", "fbs_trbxes", ["supply_id"])
    op.create_index("ix_fbs_trbxes_wb_trbx_id", "fbs_trbxes", ["wb_trbx_id"])

    op.create_foreign_key(
        "fk_fbs_orders_trbx_id",
        "fbs_orders",
        "fbs_trbxes",
        ["trbx_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_fbs_orders_trbx_id", "fbs_orders", ["trbx_id"])


def downgrade() -> None:
    op.drop_index("ix_fbs_orders_trbx_id", table_name="fbs_orders")
    op.drop_constraint("fk_fbs_orders_trbx_id", "fbs_orders", type_="foreignkey")
    op.drop_index("ix_fbs_trbxes_wb_trbx_id", table_name="fbs_trbxes")
    op.drop_index("ix_fbs_trbxes_supply_id", table_name="fbs_trbxes")
    op.drop_table("fbs_trbxes")
