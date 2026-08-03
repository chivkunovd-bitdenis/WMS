"""Add the PVZ trbx packaging-box foreign key.

Revision ID: 20260803_0069
Revises: 20260802_0068
"""

from __future__ import annotations

from alembic import op

revision = "20260803_0069"
down_revision = "20260802_0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_fbs_trbxes_packaging_box_id",
        "fbs_trbxes",
        "warehouse_boxes",
        ["packaging_box_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fbs_trbxes_packaging_box_id",
        "fbs_trbxes",
        ["packaging_box_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fbs_trbxes_packaging_box_id",
        table_name="fbs_trbxes",
    )
    op.drop_constraint(
        "fk_fbs_trbxes_packaging_box_id",
        "fbs_trbxes",
        type_="foreignkey",
    )
