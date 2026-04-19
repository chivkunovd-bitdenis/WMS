"""inbound verification actual_qty and statuses

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-15

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, Sequence[str], None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_requests",
        sa.Column("primary_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inbound_intake_requests",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inbound_intake_requests",
        sa.Column(
            "has_discrepancy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "inbound_intake_lines",
        sa.Column("actual_qty", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inbound_intake_lines", "actual_qty")
    op.drop_column("inbound_intake_requests", "has_discrepancy")
    op.drop_column("inbound_intake_requests", "verified_at")
    op.drop_column("inbound_intake_requests", "primary_accepted_at")

