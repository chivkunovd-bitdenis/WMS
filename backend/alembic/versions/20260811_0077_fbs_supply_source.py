"""Track FBS supply source.

Revision ID: 20260811_0077
Revises: 20260810_0077
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0077"
down_revision: str | Sequence[str] | None = "20260810_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fbs_supplies",
        sa.Column(
            "source",
            sa.String(length=16),
            server_default="wms",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("fbs_supplies", "source")
