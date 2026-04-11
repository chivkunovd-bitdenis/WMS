"""inbound intake request created_by_seller_id

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
