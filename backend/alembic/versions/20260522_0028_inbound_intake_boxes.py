"""inbound intake boxes with internal barcodes

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, Sequence[str], None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inbound_intake_boxes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("box_number", sa.Integer(), nullable=False),
        sa.Column("internal_barcode", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("label_printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["inbound_intake_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "box_number",
            name="uq_inbound_intake_box_req_num",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "internal_barcode",
            name="uq_inbound_intake_box_tenant_barcode",
        ),
    )
    op.create_index(
        "ix_inbound_intake_boxes_request_id",
        "inbound_intake_boxes",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_intake_boxes_request_id", table_name="inbound_intake_boxes")
    op.drop_table("inbound_intake_boxes")
