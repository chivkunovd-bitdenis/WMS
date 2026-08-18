"""Inbound seller waybill number.

Revision ID: 20260814_0081
Revises: 20260813_0080
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0081"
down_revision: str | Sequence[str] | None = "20260813_0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_requests",
        sa.Column("waybill_number", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inbound_intake_requests", "waybill_number")
