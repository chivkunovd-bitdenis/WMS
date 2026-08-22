"""Add the explicit tenant billing activation date."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260822_0096"
down_revision: str | Sequence[str] | None = "20260822_0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("billing_enabled_from", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "billing_enabled_from")
