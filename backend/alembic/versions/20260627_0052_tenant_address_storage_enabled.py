"""tenant address_storage_enabled flag

Revision ID: 20260627_0052
Revises: 20260626_0051
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260627_0052"
down_revision = "20260626_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "address_storage_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "address_storage_enabled")
