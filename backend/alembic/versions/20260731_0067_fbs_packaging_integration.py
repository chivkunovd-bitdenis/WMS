"""Down_revision: 20260730_0066_fbs_trbx"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0067_fbs_packaging_integration"
down_revision: str | Sequence[str] | None = "20260730_0066_fbs_trbx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fbs_supplies",
        sa.Column("packaging_task_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_supplies_packaging_task_id",
        "fbs_supplies",
        "packaging_tasks",
        ["packaging_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fbs_supplies_tenant_packaging_task",
        "fbs_supplies",
        ["tenant_id", "packaging_task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fbs_supplies_tenant_packaging_task", table_name="fbs_supplies")
    op.drop_constraint(
        "fk_fbs_supplies_packaging_task_id", "fbs_supplies", type_="foreignkey"
    )
    op.drop_column("fbs_supplies", "packaging_task_id")
