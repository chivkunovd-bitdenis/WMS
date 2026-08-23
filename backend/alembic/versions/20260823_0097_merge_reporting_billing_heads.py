"""Merge canonical reporting and billing heads before storage tables."""

from __future__ import annotations

from collections.abc import Sequence

revision = "20260823_0097"
down_revision: str | Sequence[str] | None = ("20260823_0096", "20260822_09c")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
