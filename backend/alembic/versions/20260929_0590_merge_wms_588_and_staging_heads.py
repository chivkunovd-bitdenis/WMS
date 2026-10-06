"""Merge the WMS-588 and staging migration histories.

Revision ID: 20260929_0590
Revises: 20260929_0565, 20260929_0589
Create Date: 2026-09-29

"""
from collections.abc import Sequence


# revision identifiers, used by Alembic.
revision: str = "20260929_0590"
down_revision: str | Sequence[str] | None = ("20260929_0565", "20260929_0589")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
