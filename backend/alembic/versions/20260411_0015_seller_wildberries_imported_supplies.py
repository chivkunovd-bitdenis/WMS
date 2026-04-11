"""seller_wildberries_imported_supplies

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_wildberries_imported_supplies",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("external_key", sa.String(length=64), nullable=False),
        sa.Column("wb_supply_id", sa.BigInteger(), nullable=True),
        sa.Column("wb_preorder_id", sa.BigInteger(), nullable=True),
        sa.Column("status_id", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("seller_id", "external_key", name="uq_wb_imported_supply_seller_key"),
    )
    op.create_index(
        op.f("ix_seller_wildberries_imported_supplies_tenant_id"),
        "seller_wildberries_imported_supplies",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_seller_wildberries_imported_supplies_seller_id"),
        "seller_wildberries_imported_supplies",
        ["seller_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_seller_wildberries_imported_supplies_seller_id"),
        table_name="seller_wildberries_imported_supplies",
    )
    op.drop_index(
        op.f("ix_seller_wildberries_imported_supplies_tenant_id"),
        table_name="seller_wildberries_imported_supplies",
    )
    op.drop_table("seller_wildberries_imported_supplies")
