"""Merge the deployed chat history with the TSD release migration head.

Revision ID: 20260913_0307
Revises: 20260911_0305, 20260913_0306
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "20260913_0307"
down_revision: str | Sequence[str] | None = ("20260911_0305", "20260913_0306")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """The parent migrations already contain the schema changes."""


def downgrade() -> None:
    """The merge revision has no schema changes to undo."""
