"""inbound box intake lines and box open/close timestamps

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, Sequence[str], None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_boxes",
        sa.Column("intake_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "inbound_intake_boxes",
        sa.Column("intake_closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "inbound_intake_box_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["box_id"], ["inbound_intake_boxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "box_id",
            "product_id",
            name="uq_inbound_intake_box_line_box_product",
        ),
    )
    op.create_index(
        "ix_inbound_intake_box_lines_box_id",
        "inbound_intake_box_lines",
        ["box_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_intake_box_lines_box_id", table_name="inbound_intake_box_lines")
    op.drop_table("inbound_intake_box_lines")
    op.drop_column("inbound_intake_boxes", "intake_closed_at")
    op.drop_column("inbound_intake_boxes", "intake_opened_at")
