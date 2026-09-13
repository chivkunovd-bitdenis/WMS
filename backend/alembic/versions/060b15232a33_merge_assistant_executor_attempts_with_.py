"""merge assistant executor attempts with staging head

Revision ID: 060b15232a33
Revises: 20260913_0307, 20260913_2200
Create Date: 2026-09-14 00:08:13.218050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '060b15232a33'
down_revision: Union[str, Sequence[str], None] = ('20260913_0307', '20260913_2200')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
