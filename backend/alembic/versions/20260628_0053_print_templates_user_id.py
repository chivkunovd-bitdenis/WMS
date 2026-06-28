"""print_templates user_id

Revision ID: 20260628_0053
Revises: 20260627_0052
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260628_0053"
down_revision = "20260627_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "print_templates",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_print_templates_user_id_users",
        "print_templates",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_print_templates_user_id", "print_templates", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_print_templates_user_id", table_name="print_templates")
    op.drop_constraint("fk_print_templates_user_id_users", "print_templates", type_="foreignkey")
    op.drop_column("print_templates", "user_id")
