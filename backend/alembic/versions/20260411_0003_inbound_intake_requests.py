"""inbound intake requests

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inbound_intake_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inbound_intake_requests_tenant_id"),
        "inbound_intake_requests",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_inbound_intake_requests_warehouse_id"),
        "inbound_intake_requests",
        ["warehouse_id"],
    )

    op.create_table(
        "inbound_intake_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("expected_qty", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["inbound_intake_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "product_id",
            name="uq_inbound_intake_line_req_product",
        ),
    )
    op.create_index(
        op.f("ix_inbound_intake_lines_request_id"),
        "inbound_intake_lines",
        ["request_id"],
    )
    op.create_index(
        op.f("ix_inbound_intake_lines_product_id"),
        "inbound_intake_lines",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_inbound_intake_lines_product_id"), table_name="inbound_intake_lines"
    )
    op.drop_index(
        op.f("ix_inbound_intake_lines_request_id"), table_name="inbound_intake_lines"
    )
    op.drop_table("inbound_intake_lines")
    op.drop_index(
        op.f("ix_inbound_intake_requests_warehouse_id"),
        table_name="inbound_intake_requests",
    )
    op.drop_index(
        op.f("ix_inbound_intake_requests_tenant_id"),
        table_name="inbound_intake_requests",
    )
    op.drop_table("inbound_intake_requests")
