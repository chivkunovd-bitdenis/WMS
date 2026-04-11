"""outbound shipment line shipped_qty (partial ship)

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outbound_shipment_lines",
        sa.Column("shipped_qty", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column(
        "outbound_shipment_lines",
        "shipped_qty",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("outbound_shipment_lines", "shipped_qty")
