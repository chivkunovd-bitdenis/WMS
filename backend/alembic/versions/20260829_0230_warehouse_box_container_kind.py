"""Distinguish warehouse boxes from warehouse cargo places.

Revision ID: 20260829_0230
Revises: 20260828_0221
Create Date: 2026-08-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260829_0230"
down_revision: str | Sequence[str] | None = "20260828_0221"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "warehouse_boxes",
        sa.Column(
            "container_kind",
            sa.String(length=32),
            server_default="box",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_warehouse_boxes_container_kind",
        "warehouse_boxes",
        "container_kind IN ('box', 'cargo_place')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_warehouse_boxes_container_kind",
        "warehouse_boxes",
        type_="check",
    )
    op.drop_column("warehouse_boxes", "container_kind")
