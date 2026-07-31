"""FBS marketplace token on seller_wildberries_credentials.

Revision ID: 20260730_0063
Revises: 20260730_0062
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260730_0063"
down_revision = "20260730_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "seller_wildberries_credentials",
        sa.Column("marketplace_token_encrypted", sa.String(length=4096), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("seller_wildberries_credentials", "marketplace_token_encrypted")
