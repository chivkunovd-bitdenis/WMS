"""Track WB marketplace-scope check result on seller_wildberries_credentials.

A seller enters one WB API key that is meant to cover everything: content,
products, FBS orders, supplies and stock. Instead of asking for a second
"marketplace" key, we record whether the last live check of the Marketplace API
scope for the stored key passed, so the UI can honestly tell the seller when
their key lacks that scope and needs to be reissued with full permissions in
the WB cabinet.

Revision ID: 20260816_0088
Revises: 20260816_0087
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260816_0088"
down_revision: str | Sequence[str] | None = "20260816_0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "seller_wildberries_credentials",
        sa.Column("marketplace_scope_ok", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "seller_wildberries_credentials",
        sa.Column(
            "marketplace_scope_checked_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("seller_wildberries_credentials", "marketplace_scope_checked_at")
    op.drop_column("seller_wildberries_credentials", "marketplace_scope_ok")
