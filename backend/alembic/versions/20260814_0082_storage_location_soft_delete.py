"""Storage location soft delete.

Revision ID: 20260814_0082
Revises: 20260814_0081
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0082"
down_revision: str | Sequence[str] | None = "20260814_0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "storage_locations",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("storage_locations", "deleted_at")
