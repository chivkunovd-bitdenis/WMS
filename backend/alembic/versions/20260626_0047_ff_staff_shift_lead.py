"""ff_staff_permissions shift_lead for marking reprint queue

Revision ID: 20260626_0047
Revises: 20260626_0046
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0047"
down_revision = "20260626_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ff_staff_permissions",
        sa.Column("can_shift_lead", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("ff_staff_permissions", "can_shift_lead", server_default=None)


def downgrade() -> None:
    op.drop_column("ff_staff_permissions", "can_shift_lead")
