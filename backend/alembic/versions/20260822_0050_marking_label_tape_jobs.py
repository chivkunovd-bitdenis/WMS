"""Add idempotent marking label tape jobs and expiring print assets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260822_0050"
down_revision: str | Sequence[str] | None = "20260821_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("background_jobs", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index(
        "uq_background_jobs_active_idempotency",
        "background_jobs",
        ["tenant_id", "job_type", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
        sqlite_where=sa.text("status IN ('pending', 'running')"),
    )
    op.add_column("fbs_print_assets", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("fbs_print_assets", "expires_at")
    op.drop_index("uq_background_jobs_active_idempotency", table_name="background_jobs")
    op.drop_column("background_jobs", "idempotency_key")
