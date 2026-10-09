"""Merge the WMS-686 and WMS-722 heads of the 09.10.2026 stage candidate.

Both revisions descend from 20261007_2303: WMS-686 (FBO KIZ move to the INB pass)
and WMS-722 (retain history when an empty supply card is removed). No schema
operations: both branches are kept as they were written.

Revision ID: 20261009_0732
Revises: 20261009_0686, 20261009_0722
"""

from collections.abc import Sequence

revision: str = "20261009_0732"
down_revision: str | Sequence[str] | None = ("20261009_0686", "20261009_0722")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
