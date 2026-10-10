"""Merge the FBO staging and etalon release migration heads.

Revision ID: 20261010_0733_stage_merge
Revises: 20261009_0732, 20261010_0723
"""

from collections.abc import Sequence

revision: str = "20261010_0733_stage_merge"
down_revision: str | Sequence[str] | None = ("20261009_0732", "20261010_0723")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
