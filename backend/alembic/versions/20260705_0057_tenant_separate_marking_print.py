"""tenant separate_marking_print_enabled flag

Revision ID: 20260705_0057
Revises: 20260701_0056
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260705_0057"
down_revision = "20260701_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "separate_marking_print_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "separate_marking_print_enabled")
