"""seller_marking_credentials (encrypted ЧЗ/СУЗ/МП tokens)

Revision ID: 20260626_0051
Revises: 20260626_0050
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0051"
down_revision = "20260626_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seller_marking_credentials",
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("cz_token_enc", sa.String(length=4096), nullable=True),
        sa.Column("suz_oms_token_enc", sa.String(length=4096), nullable=True),
        sa.Column("marketplace", sa.String(length=32), nullable=True),
        sa.Column("mp_api_key_enc", sa.String(length=4096), nullable=True),
        sa.Column("mchd_id", sa.String(length=255), nullable=True),
        sa.Column("mchd_valid_until", sa.Date(), nullable=True),
        sa.Column(
            "signing_method",
            sa.String(length=32),
            server_default="manual",
            nullable=False,
        ),
        sa.Column(
            "edo_route",
            sa.String(length=64),
            server_default="edo_light_roaming_diadoc",
            nullable=False,
        ),
        sa.Column(
            "auto_introduce",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("auto_emit_limit", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("seller_id"),
    )
    op.create_index(
        "ix_seller_marking_credentials_tenant_id",
        "seller_marking_credentials",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_seller_marking_credentials_tenant_id", table_name="seller_marking_credentials")
    op.drop_table("seller_marking_credentials")
