"""seller wildberries credentials (encrypted tokens)

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_wildberries_credentials",
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content_token_encrypted", sa.String(length=4096), nullable=True),
        sa.Column("supplies_token_encrypted", sa.String(length=4096), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("seller_id"),
    )


def downgrade() -> None:
    op.drop_table("seller_wildberries_credentials")
