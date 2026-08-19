"""tenant fbs_packing_required flag

Revision ID: 20260828_0105
Revises: 20260827_0104
Create Date: 2026-08-28

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260828_0105"
down_revision = "20260827_0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # По умолчанию true — сохраняет текущее поведение (упаковка обязательна)
    # для всех существующих тенантов, пока владелец явно не выключит требование.
    op.add_column(
        "tenants",
        sa.Column(
            "fbs_packing_required",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "fbs_packing_required")
