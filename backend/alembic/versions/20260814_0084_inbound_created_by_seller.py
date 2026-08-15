"""Track seller-created inbound requests.

Revision ID: 20260814_0084
Revises: 20260814_0083
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0084"
down_revision: str | Sequence[str] | None = "20260814_0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_requests",
        sa.Column("created_by_seller_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_inbound_intake_requests_created_by_seller_id"),
        "inbound_intake_requests",
        ["created_by_seller_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_inbound_intake_requests_created_by_seller_id",
        "inbound_intake_requests",
        "sellers",
        ["created_by_seller_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inbound_intake_requests_created_by_seller_id",
        "inbound_intake_requests",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_inbound_intake_requests_created_by_seller_id"),
        table_name="inbound_intake_requests",
    )
    op.drop_column("inbound_intake_requests", "created_by_seller_id")
