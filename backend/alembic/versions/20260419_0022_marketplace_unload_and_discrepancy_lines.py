"""marketplace_unload_lines and discrepancy_act_lines

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-19

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, Sequence[str], None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketplace_unload_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["marketplace_unload_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "product_id",
            name="uq_marketplace_unload_line_req_product",
        ),
    )
    op.create_index(
        op.f("ix_marketplace_unload_lines_request_id"),
        "marketplace_unload_lines",
        ["request_id"],
    )
    op.create_index(
        op.f("ix_marketplace_unload_lines_product_id"),
        "marketplace_unload_lines",
        ["product_id"],
    )

    op.create_table(
        "discrepancy_act_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("act_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["act_id"], ["discrepancy_acts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "act_id",
            "product_id",
            name="uq_discrepancy_act_line_act_product",
        ),
    )
    op.create_index(
        op.f("ix_discrepancy_act_lines_act_id"),
        "discrepancy_act_lines",
        ["act_id"],
    )
    op.create_index(
        op.f("ix_discrepancy_act_lines_product_id"),
        "discrepancy_act_lines",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_discrepancy_act_lines_product_id"), table_name="discrepancy_act_lines")
    op.drop_index(op.f("ix_discrepancy_act_lines_act_id"), table_name="discrepancy_act_lines")
    op.drop_table("discrepancy_act_lines")
    op.drop_index(
        op.f("ix_marketplace_unload_lines_product_id"),
        table_name="marketplace_unload_lines",
    )
    op.drop_index(
        op.f("ix_marketplace_unload_lines_request_id"),
        table_name="marketplace_unload_lines",
    )
    op.drop_table("marketplace_unload_lines")
