"""Merge the no-distribution and operational-warehouse migration heads."""

from collections.abc import Sequence

revision = "20260823_0095"
down_revision: str | Sequence[str] | None = (
    "20260821_0094",
    "20260822_0094",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
