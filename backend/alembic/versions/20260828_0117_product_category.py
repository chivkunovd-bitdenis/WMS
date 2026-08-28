"""Add the nullable WB product category.

Revision ID: 20260828_0117
Revises: 20260828_0116
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0117"
down_revision: str | Sequence[str] | None = "20260828_0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("category", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "category")
