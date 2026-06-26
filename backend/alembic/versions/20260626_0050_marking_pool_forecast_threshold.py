"""marking_pools.forecast_days_threshold

Revision ID: 20260626_0050
Revises: 20260626_0049
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0050"
down_revision = "20260626_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marking_pools",
        sa.Column("forecast_days_threshold", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marking_pools", "forecast_days_threshold")
