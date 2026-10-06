"""WMS-612 merge staging assistant and reviewed warehouse migrations.

Revision ID: 20261001_0612
Revises: 20260929_0590, 20260930_0567
"""

from collections.abc import Sequence

revision: str = "20261001_0612"
down_revision: str | Sequence[str] | None = ("20260929_0590", "20260930_0567")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
