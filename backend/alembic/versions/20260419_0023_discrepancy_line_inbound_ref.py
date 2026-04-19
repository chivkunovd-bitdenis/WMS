"""discrepancy_act_lines.inbound_intake_line_id

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-19

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, Sequence[str], None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "discrepancy_act_lines",
        sa.Column("inbound_intake_line_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_discrepancy_act_lines_inbound_intake_line_id"),
        "discrepancy_act_lines",
        ["inbound_intake_line_id"],
    )
    op.create_foreign_key(
        op.f("fk_discrepancy_act_lines_inbound_intake_line_id"),
        "discrepancy_act_lines",
        "inbound_intake_lines",
        ["inbound_intake_line_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_discrepancy_act_lines_inbound_intake_line_id"),
        "discrepancy_act_lines",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_discrepancy_act_lines_inbound_intake_line_id"),
        table_name="discrepancy_act_lines",
    )
    op.drop_column("discrepancy_act_lines", "inbound_intake_line_id")
