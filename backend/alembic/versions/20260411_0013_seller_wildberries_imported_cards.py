"""seller_wildberries_imported_cards

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_wildberries_imported_cards",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seller_id", "nm_id", name="uq_wb_imported_card_seller_nm"),
    )
    op.create_index(
        op.f("ix_seller_wildberries_imported_cards_tenant_id"),
        "seller_wildberries_imported_cards",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_seller_wildberries_imported_cards_seller_id"),
        "seller_wildberries_imported_cards",
        ["seller_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_seller_wildberries_imported_cards_seller_id"),
        table_name="seller_wildberries_imported_cards",
    )
    op.drop_index(
        op.f("ix_seller_wildberries_imported_cards_tenant_id"),
        table_name="seller_wildberries_imported_cards",
    )
    op.drop_table("seller_wildberries_imported_cards")
