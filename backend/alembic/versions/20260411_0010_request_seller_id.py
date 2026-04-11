"""inbound seller_id rename; outbound request seller_id

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_inbound_intake_requests_created_by_seller_id",
        "inbound_intake_requests",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_inbound_intake_requests_created_by_seller_id"),
        table_name="inbound_intake_requests",
    )
    op.alter_column(
        "inbound_intake_requests",
        "created_by_seller_id",
        new_column_name="seller_id",
        existing_type=sa.Uuid(as_uuid=True),
        existing_nullable=True,
    )
    op.create_index(
        op.f("ix_inbound_intake_requests_seller_id"),
        "inbound_intake_requests",
        ["seller_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_inbound_intake_requests_seller_id",
        "inbound_intake_requests",
        "sellers",
        ["seller_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text("""
        UPDATE inbound_intake_requests
        SET seller_id = (
            SELECT p.seller_id
            FROM inbound_intake_lines il
            INNER JOIN products p ON p.id = il.product_id
            WHERE il.request_id = inbound_intake_requests.id
            ORDER BY il.created_at ASC
            LIMIT 1
        )
        WHERE seller_id IS NULL
          AND EXISTS (
            SELECT 1 FROM inbound_intake_lines il2
            WHERE il2.request_id = inbound_intake_requests.id
          )
        """)
    )

    op.add_column(
        "outbound_shipment_requests",
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_outbound_shipment_requests_seller_id"),
        "outbound_shipment_requests",
        ["seller_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_outbound_shipment_requests_seller_id",
        "outbound_shipment_requests",
        "sellers",
        ["seller_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text("""
        UPDATE outbound_shipment_requests
        SET seller_id = (
            SELECT p.seller_id
            FROM outbound_shipment_lines ol
            INNER JOIN products p ON p.id = ol.product_id
            WHERE ol.request_id = outbound_shipment_requests.id
            ORDER BY ol.created_at ASC
            LIMIT 1
        )
        WHERE seller_id IS NULL
          AND EXISTS (
            SELECT 1 FROM outbound_shipment_lines ol2
            WHERE ol2.request_id = outbound_shipment_requests.id
          )
        """)
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_outbound_shipment_requests_seller_id",
        "outbound_shipment_requests",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_outbound_shipment_requests_seller_id"),
        table_name="outbound_shipment_requests",
    )
    op.drop_column("outbound_shipment_requests", "seller_id")

    op.drop_constraint(
        "fk_inbound_intake_requests_seller_id",
        "inbound_intake_requests",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_inbound_intake_requests_seller_id"),
        table_name="inbound_intake_requests",
    )
    op.alter_column(
        "inbound_intake_requests",
        "seller_id",
        new_column_name="created_by_seller_id",
        existing_type=sa.Uuid(as_uuid=True),
        existing_nullable=True,
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
