"""WMS-444: retain the picked packed source in MP boxes.

The existing pick allocation and box composition are the source of truth for an
MP unload.  These two counters preserve the already-packed portion at the
moment it is picked, so later packaging/billing never infers it from unrelated
remaining stock.

Revision ID: 20260913_0305
Revises: 20260911_0304
Create Date: 2026-09-13 03:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0305"
down_revision: str | Sequence[str] | None = "20260911_0304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "marketplace_unload_pick_allocations",
        sa.Column("quantity_packed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "marketplace_unload_box_lines",
        sa.Column("quantity_packed", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("marketplace_unload_box_lines", "quantity_packed")
    op.drop_column("marketplace_unload_pick_allocations", "quantity_packed")
