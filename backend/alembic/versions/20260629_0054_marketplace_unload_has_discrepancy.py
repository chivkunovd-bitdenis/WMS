"""marketplace unload has_discrepancy flag

Revision ID: 20260629_0054
Revises: 20260628_0053
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260629_0054"
down_revision = "20260628_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marketplace_unload_requests",
        sa.Column(
            "has_discrepancy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("marketplace_unload_requests", "has_discrepancy")
