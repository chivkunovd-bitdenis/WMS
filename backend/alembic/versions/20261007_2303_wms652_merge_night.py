"""WMS-652: merge the independently applied night migration heads.

Revision ID: 20261007_2303
Revises: 20261003_0001, 20261005_0658b, 20261007_2302
"""

from collections.abc import Sequence

revision: str = "20261007_2303"
down_revision: str | Sequence[str] | None = (
    "20261003_0001",
    "20261005_0658b",
    "20261007_2302",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
