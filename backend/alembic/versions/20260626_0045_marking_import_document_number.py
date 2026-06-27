"""marking_code_imports document_number

Revision ID: 20260626_0045
Revises: 20260626_0044
Create Date: 2026-06-26

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0045"
down_revision = "20260626_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marking_code_imports",
        sa.Column("document_number", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marking_code_imports", "document_number")
