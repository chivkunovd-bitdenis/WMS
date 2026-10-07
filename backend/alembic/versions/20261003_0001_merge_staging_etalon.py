"""Merge staging and production etalon heads after the 03.10.2026 sync.

Staging carries the applied WMS-433/593/594/612 history ending in 20261001_0612;
production etalon adds WMS-624 developer requests in 20261001_2301. No schema
operations: both branches are kept as they were applied.

Revision ID: 20261003_0001
Revises: 20261001_0612, 20261001_2301
"""

from collections.abc import Sequence

revision: str = "20261003_0001"
down_revision: str | Sequence[str] | None = ("20261001_0612", "20261001_2301")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
