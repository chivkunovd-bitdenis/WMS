"""Exclude technical FBS routing warehouses from physical storage billing."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260823_0098"
down_revision: str | Sequence[str] | None = "20260823_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The earlier warehouse migration handled suffixed routing stubs, but the
    # canonical unsuffixed ``FBS WB`` name also exists in real installations.
    # Storage statements and tariffs must only use physical warehouses.
    op.execute(
        sa.text(
            """
            UPDATE warehouses
            SET is_operational = FALSE
            WHERE lower(name) = 'fbs wb'
               OR lower(name) LIKE 'fbs wb %'
               OR lower(code) = 'fbs-wb'
               OR lower(code) LIKE 'fbs-wb-%'
            """
        )
    )


def downgrade() -> None:
    # Classification is business data. Re-enabling a technical route on
    # downgrade would incorrectly expose it as a physical storage warehouse.
    pass
