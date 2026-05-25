"""inbound intake planned and actual box counts

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, Sequence[str], None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_requests",
        sa.Column("planned_box_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inbound_intake_requests",
        sa.Column("actual_box_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inbound_intake_requests",
        sa.Column(
            "boxes_discrepancy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("inbound_intake_requests", "boxes_discrepancy")
    op.drop_column("inbound_intake_requests", "actual_box_count")
    op.drop_column("inbound_intake_requests", "planned_box_count")
