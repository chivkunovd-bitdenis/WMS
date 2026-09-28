"""WMS-517: durable preparation state and per-attempt preflight evidence."""

import sqlalchemy as sa

from alembic import op

revision = "20260924_0519"
down_revision = "20260923_0518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preparation/auth state needed to resume an operation across API restarts.
    for column in (
        sa.Column("workflow_lease_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workflow_error", sa.JSON(), nullable=True),
        sa.Column("auth_signature_hash", sa.String(64), nullable=True),
        sa.Column("attempt_started_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("withdrawal_operations", column)
    op.add_column("withdrawal_items", sa.Column("preflight_evidence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("withdrawal_items", "preflight_evidence")
    for name in (
        "attempt_started_at",
        "auth_signature_hash",
        "workflow_error",
        "workflow_lease_until",
        "workflow_lease_id",
    ):
        op.drop_column("withdrawal_operations", name)
