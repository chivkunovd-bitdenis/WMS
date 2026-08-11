"""Track FBS order supplier status separately.

Revision ID: 20260810_0077
Revises: 20260809_0076
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0077"
down_revision: str | Sequence[str] | None = "20260809_0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fbs_orders",
        sa.Column("supplier_status", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fbs_orders", "supplier_status")
