"""merge alembic heads 0025 and 126fb26be297

Revision ID: 0026
Revises: 0025, 126fb26be297
Create Date: 2026-05-22

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: Union[str, Sequence[str], None] = ("0025", "126fb26be297")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
