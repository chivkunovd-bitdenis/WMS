"""seller_ozon_imported_cards

Revision ID: 20260927_0548
Revises: 20260924_0526
Create Date: 2026-09-27

WMS-548 D3: snapshot of the seller's Ozon catalog, by the same shape as
``seller_wildberries_imported_cards`` (0013) — see that table's model docstring
for why a snapshot is needed instead of reusing ``product_marketplace_links``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_0548"
down_revision: Union[str, Sequence[str], None] = "20260924_0526"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_ozon_imported_cards",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("ozon_product_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=True),
        sa.Column("offer_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=True),
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
        sa.UniqueConstraint(
            "seller_id", "ozon_product_id", name="uq_ozon_imported_card_seller_product"
        ),
    )
    op.create_index(
        op.f("ix_seller_ozon_imported_cards_tenant_id"),
        "seller_ozon_imported_cards",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_seller_ozon_imported_cards_seller_id"),
        "seller_ozon_imported_cards",
        ["seller_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_seller_ozon_imported_cards_seller_id"),
        table_name="seller_ozon_imported_cards",
    )
    op.drop_index(
        op.f("ix_seller_ozon_imported_cards_tenant_id"),
        table_name="seller_ozon_imported_cards",
    )
    op.drop_table("seller_ozon_imported_cards")
