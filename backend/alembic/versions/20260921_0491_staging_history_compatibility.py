"""Recognize the historic staging WMS-489 merge stamp without its assistant branch.

Revision ID: 20260921_0491
Revises: 20260921_0490

Historic staging already used this exact revision ID for a merge of
``20260921_0490`` and the staging-only assistant revision ``060b15232a33``.
The release candidate intentionally does not contain that assistant branch, but
it must still recognize databases stamped at the historic merge revision.
Production databases at ``20260921_0490`` traverse this no-op before later
migrations; old staging databases stamped at ``20260921_0491`` continue from it.
"""

from __future__ import annotations


revision = "20260921_0491"
down_revision = "20260921_0490"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Compatibility-only revision: 0490 owns the WMS-489 DDL. The omitted
    # assistant branch is neither applied nor imported into this graph.
    pass


def downgrade() -> None:
    # Alembic only moves the version stamp back to 0490. Any assistant schema
    # already present in an old staging database remains untouched because this
    # release line neither owns nor can safely reverse that staging-only DDL.
    pass
