"""Merge staging login/assistant and WMS-489 migration heads.

Revision ID: 20260921_0491
Revises: 060b15232a33, 20260921_0490
"""

from __future__ import annotations


revision = "20260921_0491"
down_revision = ("060b15232a33", "20260921_0490")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge-only revision: both parent chains own their DDL.
    pass


def downgrade() -> None:
    # Alembic splits the heads again; neither parent migration is reversed here.
    pass
