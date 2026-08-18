"""Inbound cargo places and product weight.

Revision ID: 20260814_0083
Revises: 20260814_0082
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260814_0083"
down_revision: str | Sequence[str] | None = "20260814_0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("weight_g", sa.Integer(), nullable=True))
    op.create_table(
        "inbound_intake_cargo_places",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("place_number", sa.Integer(), nullable=False),
        sa.Column("internal_barcode", sa.String(length=64), nullable=False),
        sa.Column("label_printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["inbound_intake_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "place_number",
            name="uq_inbound_intake_cargo_place_req_num",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "internal_barcode",
            name="uq_inbound_intake_cargo_place_tenant_barcode",
        ),
    )
    op.create_index(
        "ix_inbound_intake_cargo_places_request_id",
        "inbound_intake_cargo_places",
        ["request_id"],
    )
    op.create_index(
        "ix_inbound_intake_cargo_places_tenant_id",
        "inbound_intake_cargo_places",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inbound_intake_cargo_places_tenant_id",
        table_name="inbound_intake_cargo_places",
    )
    op.drop_index(
        "ix_inbound_intake_cargo_places_request_id",
        table_name="inbound_intake_cargo_places",
    )
    op.drop_table("inbound_intake_cargo_places")
    op.drop_column("products", "weight_g")
