"""users.must_set_password for seller first-login password setup

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-18

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_set_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("users", "must_set_password", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "must_set_password")
