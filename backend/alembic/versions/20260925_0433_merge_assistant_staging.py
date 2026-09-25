"""WMS-433: merge assistant queue and current staging migrations."""

from collections.abc import Sequence

revision: str = "20260925_0433"
down_revision: str | Sequence[str] | None = ("20260913_2200", "20260924_0526")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
