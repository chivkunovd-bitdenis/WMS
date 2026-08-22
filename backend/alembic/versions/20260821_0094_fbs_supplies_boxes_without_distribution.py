"""fbs_supplies: сохраняемый режим «без распределения»"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260821_0094"
down_revision = "20260821_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fbs_supplies",
        sa.Column("boxes_without_distribution_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fbs_supplies",
        sa.Column("boxes_without_distribution_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_supplies_boxes_without_distribution_by_user_id",
        "fbs_supplies",
        "users",
        ["boxes_without_distribution_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fbs_supplies_boxes_without_distribution_by_user_id",
        "fbs_supplies",
        type_="foreignkey",
    )
    op.drop_column("fbs_supplies", "boxes_without_distribution_by_user_id")
    op.drop_column("fbs_supplies", "boxes_without_distribution_at")
