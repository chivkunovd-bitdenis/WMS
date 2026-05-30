"""packaging task pick resync warning flag

Revision ID: 0037
Revises: 0036
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "packaging_tasks",
        sa.Column(
            "pick_resync_warning",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("packaging_tasks", "pick_resync_warning", server_default=None)


def downgrade() -> None:
    op.drop_column("packaging_tasks", "pick_resync_warning")
