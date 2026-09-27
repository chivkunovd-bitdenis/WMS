"""WMS-517: preserve original GS1 while claiming the provider KI identity."""

import sqlalchemy as sa

from alembic import op

revision = "20260924_0520"
down_revision = "20260924_0519"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("withdrawal_items", sa.Column("provider_cis", sa.String(74), nullable=True))
    # Historical signed payloads stay immutable; new attempts derive KI server-side.
    op.create_index(
        "uq_withdrawal_provider_claim",
        "withdrawal_items",
        ["tenant_id", "provider_cis"],
        unique=True,
        postgresql_where=sa.text("holds_claim AND provider_cis IS NOT NULL"),
        sqlite_where=sa.text("holds_claim = 1 AND provider_cis IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_withdrawal_provider_claim", table_name="withdrawal_items")
    op.drop_column("withdrawal_items", "provider_cis")
