"""marketplace_unload_requests and discrepancy_acts

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-19

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, Sequence[str], None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketplace_unload_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_marketplace_unload_requests_tenant_id"),
        "marketplace_unload_requests",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_marketplace_unload_requests_warehouse_id"),
        "marketplace_unload_requests",
        ["warehouse_id"],
    )
    op.create_index(
        op.f("ix_marketplace_unload_requests_seller_id"),
        "marketplace_unload_requests",
        ["seller_id"],
    )

    op.create_table(
        "discrepancy_acts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("inbound_intake_request_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["inbound_intake_request_id"],
            ["inbound_intake_requests.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_discrepancy_acts_tenant_id"),
        "discrepancy_acts",
        ["tenant_id"],
    )
    op.create_index(
        op.f("ix_discrepancy_acts_inbound_intake_request_id"),
        "discrepancy_acts",
        ["inbound_intake_request_id"],
    )
    op.create_index(
        op.f("ix_discrepancy_acts_seller_id"),
        "discrepancy_acts",
        ["seller_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_discrepancy_acts_seller_id"), table_name="discrepancy_acts")
    op.drop_index(
        op.f("ix_discrepancy_acts_inbound_intake_request_id"),
        table_name="discrepancy_acts",
    )
    op.drop_index(op.f("ix_discrepancy_acts_tenant_id"), table_name="discrepancy_acts")
    op.drop_table("discrepancy_acts")
    op.drop_index(
        op.f("ix_marketplace_unload_requests_seller_id"),
        table_name="marketplace_unload_requests",
    )
    op.drop_index(
        op.f("ix_marketplace_unload_requests_warehouse_id"),
        table_name="marketplace_unload_requests",
    )
    op.drop_index(
        op.f("ix_marketplace_unload_requests_tenant_id"),
        table_name="marketplace_unload_requests",
    )
    op.drop_table("marketplace_unload_requests")
