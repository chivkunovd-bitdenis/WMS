"""Bring previously applied FBS packing boxes to the PVZ-aware schema.

Revision ID: 20260806_0074
Revises: 20260806_0073
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260806_0074"
down_revision: str | Sequence[str] | None = "20260806_0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fbs_packing_boxes", sa.Column("trbx_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column(
        "fbs_packing_boxes",
        sa.Column("creation_idempotency_key", sa.String(128), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_packing_boxes_trbx_id",
        "fbs_packing_boxes",
        "fbs_trbxes",
        ["trbx_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_fbs_packing_boxes_trbx", "fbs_packing_boxes", ["trbx_id"])
    op.create_index("ix_fbs_packing_boxes_trbx_id", "fbs_packing_boxes", ["trbx_id"])
    op.create_index(
        "ix_fbs_packing_boxes_creation_idempotency_key",
        "fbs_packing_boxes",
        ["supply_id", "creation_idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_fbs_packing_boxes_creation_idempotency_key", table_name="fbs_packing_boxes")
    op.drop_index("ix_fbs_packing_boxes_trbx_id", table_name="fbs_packing_boxes")
    op.drop_constraint("uq_fbs_packing_boxes_trbx", "fbs_packing_boxes", type_="unique")
    op.drop_constraint("fk_fbs_packing_boxes_trbx_id", "fbs_packing_boxes", type_="foreignkey")
    op.drop_column("fbs_packing_boxes", "creation_idempotency_key")
    op.drop_column("fbs_packing_boxes", "trbx_id")
