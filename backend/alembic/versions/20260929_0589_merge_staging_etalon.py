"""Merge staging-only WMS-433 history with the current etalon history.

Revision ID: 20260929_0589
Revises: 20260925_0433, 20260928_0564
Create Date: 2026-09-29
"""

from collections.abc import Sequence

revision: str = "20260929_0589"
down_revision: str | Sequence[str] | None = ("20260925_0433", "20260928_0564")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
