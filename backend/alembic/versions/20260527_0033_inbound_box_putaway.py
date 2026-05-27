"""inbound box putaway: posted_qty on box lines, box_id on distribution

Revision ID: 0033
Revises: 0032
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, Sequence[str], None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_box_lines",
        sa.Column("posted_qty", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inbound_intake_distribution_lines",
        sa.Column("box_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inbound_intake_distribution_lines_box_id",
        "inbound_intake_distribution_lines",
        "inbound_intake_boxes",
        ["box_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_inbound_intake_distribution_lines_box_id",
        "inbound_intake_distribution_lines",
        ["box_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inbound_intake_distribution_lines_box_id",
        table_name="inbound_intake_distribution_lines",
    )
    op.drop_constraint(
        "fk_inbound_intake_distribution_lines_box_id",
        "inbound_intake_distribution_lines",
        type_="foreignkey",
    )
    op.drop_column("inbound_intake_distribution_lines", "box_id")
    op.drop_column("inbound_intake_box_lines", "posted_qty")
